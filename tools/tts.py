"""Озвучка по сценарию: сегменты с якорями во времени -> дорожка голоса WAV + тайминги субтитров.

    .venv/Scripts/python tools/tts.py <script.json> <lang> <out_dir>

script.json:
{
  "duration_s": 59.83,
  "voices": {"en": {"engine": "kokoro", "voice": "af_heart", "speed": 1.0},
             "ru": {"engine": "edge", "voice": "ru-RU-SvetlanaNeural", "rate": "+0%"}},
  "segments": [{"at": 0.25, "en": "This dead star ...", "ru": "Эта мёртвая звезда ..."}, ...]
}
at — момент начала фразы на таймлайне ролика (с). Если фраза не успевает до следующего якоря,
скрипт ускоряет её (до ×1.25) и печатает предупреждение.

Выход: <out_dir>/vo_<lang>.wav (48 кГц, моно float), <out_dir>/captions_<lang>.json
       ([{"text", "start", "end"}] в секундах — фразами по 2–5 слов для вертикальных субтитров).

Движки:
  kokoro — Kokoro-82M (Apache-2.0, только EN), локально, веса в assets/tts/ (kokoro-v1.0.onnx, voices-v1.0.bin)
  edge   — Microsoft Edge neural voices (edge-tts, нужен интернет; коммерческое использование — серая зона ToS,
           см. docs/research). Даёт точные границы слов.
"""
import asyncio
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SR = 48000
MAX_SPEEDUP = 1.25


def resample(x, sr_in, sr_out=SR):
    if sr_in == sr_out:
        return x.astype(np.float32)
    n = int(round(len(x) * sr_out / sr_in))
    t = np.linspace(0, len(x) - 1, n)
    return np.interp(t, np.arange(len(x)), x).astype(np.float32)


def trim_silence(x, thr=0.004, pad=0.03):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * SR))
    b = min(len(x), idx[-1] + int(pad * SR))
    return x[a:b]


# ---------------------------------------------------------------- движки
_KOKORO = None


def _espeak_ascii_data():
    """espeak-ng (фонемизатор Kokoro) не читает данные по пути с кириллицей (…/Проекты/…):
    копируем espeak-ng-data в ASCII-путь (%LOCALAPPDATA%/space-shorts) и подменяем путь в загрузчике."""
    import shutil
    import espeakng_loader
    src = espeakng_loader.get_data_path()
    try:
        src.encode("ascii")
        return
    except UnicodeEncodeError:
        pass
    dst = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "space-shorts", "espeak-ng-data")
    if not os.path.exists(os.path.join(dst, "phontab")):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    espeakng_loader.get_data_path = lambda: dst
    os.environ["ESPEAK_DATA_PATH"] = dst


def tts_kokoro(text, voice="af_heart", speed=1.0, lang="en-us"):
    global _KOKORO
    _espeak_ascii_data()
    from kokoro_onnx import Kokoro
    if _KOKORO is None:
        d = os.path.join(REPO, "assets", "tts")
        _KOKORO = Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))
    samples, sr = _KOKORO.create(text, voice=voice, speed=speed, lang=lang)
    return trim_silence(resample(np.asarray(samples, np.float32), sr)), None


def tts_edge(text, voice="ru-RU-SvetlanaNeural", rate="+0%", speed=1.0):
    import edge_tts
    if speed != 1.0:
        rate = f"{int(round((speed - 1.0) * 100)):+d}%"

    async def run():
        com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        audio, words = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio.extend(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
        return bytes(audio), words
    audio, words = asyncio.run(run())
    import io
    x, sr = sf.read(io.BytesIO(audio), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    raw = resample(x, sr)
    # границы слов — относительно начала после обрезки тишины
    idx = np.where(np.abs(raw) > 0.004)[0]
    lead = max(0, idx[0] - int(0.03 * SR)) / SR if len(idx) else 0.0
    return trim_silence(raw), [(a - lead, b - lead, w) for a, b, w in words]


def synth(text, cfg, speed=1.0):
    if cfg["engine"] == "kokoro":
        return tts_kokoro(text, cfg.get("voice", "af_heart"), cfg.get("speed", 1.0) * speed, cfg.get("lang", "en-us"))
    if cfg["engine"] == "edge":
        return tts_edge(text, cfg.get("voice", "ru-RU-SvetlanaNeural"), cfg.get("rate", "+0%"),
                        cfg.get("speed", 1.0) * speed)
    raise ValueError(cfg["engine"])


# ---------------------------------------------------------------- субтитры
def chunk_words(text, max_chars=22, max_words=4):
    """Фразы для вертикальных субтитров: 2–4 слова, не длиннее max_chars, разрыв на знаках препинания."""
    words = text.split()
    out, cur = [], []
    for w in words:
        cand = " ".join(cur + [w])
        if cur and (len(cand) > max_chars or len(cur) >= max_words):
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.,:;!?—]$", w) and len(cur) >= 2:
            out.append(cur)
            cur = []
    if cur:
        if out and len(cur) == 1 and len(" ".join(out[-1] + cur)) <= max_chars + 6:
            out[-1] += cur
        else:
            out.append(cur)
    return out


def caption_times(chunks, dur, words=None):
    """Время фраз: по границам слов (edge) или пропорционально числу символов (kokoro)."""
    if words and len(words) >= sum(len(c) for c in chunks):
        res, k = [], 0
        for c in chunks:
            a = words[k][0]
            b = words[k + len(c) - 1][1]
            res.append((a, b))
            k += len(c)
        return res
    lens = [len(" ".join(c)) + 1 for c in chunks]
    tot = sum(lens)
    t, res = 0.0, []
    for L in lens:
        d = dur * L / tot
        res.append((t, t + d))
        t += d
    return res


def main(script_path, lang, out_dir):
    sc = json.load(open(script_path, encoding="utf-8"))
    cfg = sc["voices"][lang]
    total = sc["duration_s"]
    track = np.zeros(int(total * SR) + SR, np.float32)
    caps, report = [], []
    segs = sc["segments"]
    for i, seg in enumerate(segs):
        text = seg[lang]
        at = seg["at"]
        limit = (segs[i + 1]["at"] if i + 1 < len(segs) else total) - at - 0.15
        speed = 1.0
        x, words = synth(text, cfg, speed)
        dur = len(x) / SR
        if dur > limit:
            speed = min(MAX_SPEEDUP, dur / limit * 1.02)
            x, words = synth(text, cfg, speed)
            dur = len(x) / SR
        a = int(at * SR)
        b = min(len(track), a + len(x))
        track[a:b] += x[: b - a]
        chunks = chunk_words(text)
        for (s0, s1), c in zip(caption_times(chunks, dur, words), chunks):
            caps.append({"text": " ".join(c), "start": round(at + s0, 3), "end": round(at + s1 + 0.12, 3)})
        status = "OK" if dur <= limit else "OVERRUN"
        report.append(f"{status} seg{i + 1} at={at:.2f}s dur={dur:.2f}s limit={limit:.2f}s speed={speed:.2f}")
    # субтитры не перекрываются: конец фразы <= начала следующей
    for p, q in zip(caps, caps[1:]):
        p["end"] = min(p["end"], q["start"])
    peak = np.max(np.abs(track)) or 1.0
    track = track[: int(total * SR)] / peak * 0.89          # −1 дБFS
    os.makedirs(out_dir, exist_ok=True)
    sf.write(os.path.join(out_dir, f"vo_{lang}.wav"), track, SR, subtype="FLOAT")
    json.dump(caps, open(os.path.join(out_dir, f"captions_{lang}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n".join(report))
    print(f"TTS {lang}: {len(segs)} сегментов, {len(caps)} фраз субтитров -> {out_dir}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
