"""Озвучка по сценарию: сегменты с якорями во времени -> дорожка голоса WAV + тайминги субтитров.

    .venv/Scripts/python tools/tts.py <script.json> <lang> <out_dir> [--max-chars N]

script.json:
{
  "duration_s": 59.83,
  "caption_max_chars": 26,                       # необязательно: длина строки субтитра (CLI --max-chars важнее)
  "voices": {"en": {"engine": "kokoro", "voice": "af_heart", "speed": 1.0},
             "ru": {"engine": "edge", "voice": "ru-RU-SvetlanaNeural", "rate": "+0%"}},
  "segments": [{"at": 0.25, "en": "This dead star ...", "ru": "...", "en_cap": "... 161 ..."}, ...]
}
at — момент начала фразы на таймлайне ролика (с); якоря строго по возрастанию, 0 ≤ at < duration_s
(иначе ValueError). <lang>_cap — текст субтитров, если он отличается от произносимого (цифры вместо слов);
«|» в нём — ручной разрыв строки. Если фраза не успевает до следующего якоря, скрипт ускоряет её
(до ×1.25) и печатает OVERRUN; если до следующего якоря ≤ 0.35 с — сразу ×1.25 и WARN (раздвинуть якоря).
voices.<lang>.speed — множитель темпа; у edge он перемножается с rate: "+10%" и ×1.1 -> "+21%".

Тайминг субтитров: edge — по границам слов (WordBoundary), сопоставление по нормализованным словам
(буквы/цифры без регистра и пунктуации; тире без звука пропускаются, слова через дефис склеиваются
независимо от того, как их разбил edge). Начало фразы не раньше начала сегмента.
kokoro и любой <lang>_cap, отличный от текста, — пропорционально числу символов (рассинхрон до 0.3–0.5 с
на длинных фразах — ожидаемо, проверять глазами).

Выход: <out_dir>/vo_<lang>.wav (48 кГц, моно float), <out_dir>/captions_<lang>.json
       ([{"text", "start", "end"}] в секундах — фразами по 2–5 слов для вертикальных субтитров).

Движки:
  kokoro — Kokoro-82M (Apache-2.0, только EN), локально, веса в assets/tts/ (kokoro-v1.0.onnx, voices-v1.0.bin)
  edge   — Microsoft Edge neural voices (edge-tts, нужен интернет; коммерческое использование — серая зона ToS,
           см. docs/research). Даёт границы слов.
Передискретизация 24 -> 48 кГц — полифазный фильтр (scipy.signal.resample_poly), без зеркальных образов.
"""
import argparse
import asyncio
import json
import os
import re

import numpy as np
import soundfile as sf

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SR = 48000
MAX_SPEEDUP = 1.25


def resample(x, sr_in, sr_out=SR):
    """Полифазная передискретизация (фильтр против зеркальных образов); длина = ceil(len·sr_out/sr_in)."""
    from math import gcd
    from scipy.signal import resample_poly
    if sr_in == sr_out:
        return x.astype(np.float32)
    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


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


def edge_rate(rate="+0%", speed=1.0):
    """rate из конфига × множитель speed -> rate для edge-tts: "+10%" и ×1.1 -> "+21%" (в пределах −50…+100%)."""
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*%\s*", str(rate))
    if not m:
        raise ValueError(f"edge rate: ожидается вида '+10%', получено {rate!r}")
    pct = ((1.0 + float(m.group(1)) / 100.0) * speed - 1.0) * 100.0
    return f"{int(round(max(-50.0, min(100.0, pct)))):+d}%"


def tts_edge(text, voice="ru-RU-SvetlanaNeural", rate="+0%", speed=1.0):
    import edge_tts
    rate = edge_rate(rate, speed)

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
    # границы слов — относительно начала после обрезки тишины; раньше начала звука слово не начинается
    idx = np.where(np.abs(raw) > 0.004)[0]
    lead = max(0, idx[0] - int(0.03 * SR)) / SR if len(idx) else 0.0
    return trim_silence(raw), [(max(0.0, a - lead), max(0.0, b - lead), w) for a, b, w in words]


def synth(text, cfg, speed=1.0):
    if cfg["engine"] == "kokoro":
        return tts_kokoro(text, cfg.get("voice", "af_heart"), cfg.get("speed", 1.0) * speed, cfg.get("lang", "en-us"))
    if cfg["engine"] == "edge":
        return tts_edge(text, cfg.get("voice", "ru-RU-SvetlanaNeural"), cfg.get("rate", "+0%"),
                        cfg.get("speed", 1.0) * speed)
    raise ValueError(cfg["engine"])


# ---------------------------------------------------------------- субтитры
FUNCTION_WORDS = {
    "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "with", "from", "than", "and", "or", "but",
    "as", "its", "it's", "their", "our", "into", "like", "that", "is", "are", "was", "yet", "only", "even",
    "и", "в", "во", "на", "с", "со", "к", "ко", "по", "о", "об", "от", "до", "из", "за", "для", "как", "но",
    "а", "что", "же", "не", "ни", "у", "при", "без", "всего", "почти",
}


def _is_unit_pair(a, b):
    """«20 km», «161 оборот», «1992 году» — число не отрывать от следующего слова."""
    return bool(re.fullmatch(r"[\d.,]+", a))


def _split_phrase(words, max_chars):
    if len(" ".join(words)) <= max_chars or len(words) <= 1:
        return [words]
    best, best_cost = None, 1e9
    for i in range(1, len(words)):
        left, right = words[:i], words[i:]
        L, R = len(" ".join(left)), len(" ".join(right))
        cost = abs(L - R) + max(0, L - max_chars) * 3 + max(0, R - max_chars) * 3
        if left[-1].lower().strip(",.") in FUNCTION_WORDS:
            cost += 25
        if _is_unit_pair(left[-1], right[0]):
            cost += 60
        if right[0].lower() in FUNCTION_WORDS:          # естественная граница: перед предлогом/союзом
            cost -= 12
        if len(left) == 1 or len(right) == 1:
            cost += 10
        if cost < best_cost:
            best, best_cost = i, cost
    return _split_phrase(words[:best], max_chars) + _split_phrase(words[best:], max_chars)


def chunk_words(text, max_chars=26):
    """Фразы для вертикальных субтитров: сначала по знакам препинания, затем сбалансированный разрез;
    служебные слова не висят в конце строки, число не отрывается от единицы/слова за ним.
    «|» в тексте — ручной разрыв (точная раскладка для сложных фраз)."""
    if "|" in text:
        return [p.split() for p in text.split("|") if p.strip()]
    phrases, cur = [], []
    for w in text.split():
        cur.append(w)
        if re.search(r"[.,:;!?]$", w) or w in ("—", "–"):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    # тире в начале фразы приклеиваем к предыдущей
    merged = []
    for p in phrases:
        if merged and p and p[0] in ("—", "–") and len(p) == 1:
            merged[-1] = merged[-1] + p
        else:
            merged.append(p)
    out = []
    for p in merged:
        out += _split_phrase(p, max_chars)
    # одиночное короткое слово — к соседу, если влезает
    res = []
    for c in out:
        if res and len(c) == 1 and len(" ".join(res[-1] + c)) <= max_chars + 4:
            res[-1] = res[-1] + c
        else:
            res.append(c)
    return res


def _norm(w):
    """Ключ слова для сопоставления: только буквы/цифры, нижний регистр, ё=е (тире, дефис, пунктуация -> '')."""
    return re.sub(r"[\W_]+", "", w.lower()).replace("ё", "е")


def _word_aligned(chunks, words):
    """Фразы -> границы слов edge по потоку нормализованных символов: у каждой буквы фразы есть слово edge
    с той же буквой потока. Поэтому «sixty-one» сопоставится, разбит ли он edge на части или нет, а тире
    без WordBoundary ничего не сдвигает. Если тексты расходятся — difflib по символам.
    Фраза без единой совпавшей буквы -> None (вызывающий переходит на тайминг по длине)."""
    import difflib
    a_txt, a_own = [], []                   # поток букв фраз и номер фразы у каждой буквы
    for ci, c in enumerate(chunks):
        for w in c:
            k = _norm(w)
            a_txt.append(k)
            a_own += [ci] * len(k)
    b_txt, b_own = [], []                   # поток букв edge и номер слова edge
    for wi, (_, _, w) in enumerate(words):
        k = _norm(w)
        b_txt.append(k)
        b_own += [wi] * len(k)
    A, B = "".join(a_txt), "".join(b_txt)
    if A == B:
        pairs = ((i, i) for i in range(len(A)))
    else:
        sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
        pairs = ((m.a + j, m.b + j) for m in sm.get_matching_blocks() for j in range(m.size))
    first, last = {}, {}
    for ia, ib in pairs:
        ci, wi = a_own[ia], b_own[ib]
        first.setdefault(ci, wi)
        last[ci] = wi
    lettered = set(a_own)
    if not lettered <= set(first):
        return None
    res, prev = [], (0.0, 0.0)
    for ci in range(len(chunks)):           # фраза без букв (только «—» после «|») — время соседа слева
        prev = (words[first[ci]][0], words[last[ci]][1]) if ci in first else (prev[1], prev[1])
        res.append(prev)
    for i in range(1, len(res)):            # монотонность начал (на случай расхождения текста)
        s0 = max(res[i][0], res[i - 1][0])
        res[i] = (s0, max(res[i][1], s0))
    return res


def caption_times(chunks, dur, words=None):
    """Время фраз (с от начала сегмента), 0 ≤ start ≤ end ≤ dur: по границам слов edge (_word_aligned),
    иначе (kokoro, <lang>_cap, несопоставимый текст) — пропорционально числу символов."""
    res = _word_aligned(chunks, words) if words else None
    if res is None:
        if words:
            print("WARN субтитры: слова edge не сопоставились с текстом — тайминг по длине")
        res = _proportional(chunks, dur)
    return [(min(max(0.0, a), dur), min(max(0.0, b), dur)) for a, b in res]


def _proportional(chunks, dur):
    lens = [len(" ".join(c)) + 1 for c in chunks]
    tot = sum(lens)
    t, res = 0.0, []
    for L in lens:
        d = dur * L / tot
        res.append((t, t + d))
        t += d
    return res


MIN_LIMIT = 0.2     # с: если на фразу остаётся меньше — якоря стоят слишком тесно


def check_anchors(segs, total):
    """Якоря: 0 ≤ at < duration_s и строго по возрастанию — иначе ValueError."""
    prev = None
    for i, seg in enumerate(segs):
        at = seg["at"]
        if not 0.0 <= at < total:
            raise ValueError(f"seg{i + 1}: at={at} вне [0, {total})")
        if prev is not None and at <= prev:
            raise ValueError(f"seg{i + 1}: at={at} не больше предыдущего якоря ({prev})")
        prev = at


def main(script_path, lang, out_dir, max_chars=None):
    """max_chars (длина строки субтитра): аргумент/CLI > script["caption_max_chars"] > 26."""
    sc = json.load(open(script_path, encoding="utf-8"))
    cfg = sc["voices"][lang]
    total = sc["duration_s"]
    max_chars = int(max_chars or sc.get("caption_max_chars") or 26)
    track = np.zeros(int(total * SR) + SR, np.float32)
    caps, report = [], []
    segs = sc["segments"]
    check_anchors(segs, total)
    for i, seg in enumerate(segs):
        text = seg[lang]
        at = seg["at"]
        limit = (segs[i + 1]["at"] if i + 1 < len(segs) else total) - at - 0.15
        speed = 1.0
        x, words = synth(text, cfg, speed)
        dur = len(x) / SR
        if dur > limit:
            if limit <= MIN_LIMIT:
                print(f"WARN seg{i + 1}: до следующего якоря {limit + 0.15:.2f} с — раздвинь якоря")
                speed = MAX_SPEEDUP
            else:
                speed = min(MAX_SPEEDUP, dur / limit * 1.02)
            x, words = synth(text, cfg, speed)
            dur = len(x) / SR
        a = int(at * SR)
        b = min(len(track), a + len(x))
        track[a:b] += x[: b - a]
        # текст субтитров может отличаться от произносимого (цифры вместо слов): тогда тайминг — по длине
        cap_text = seg.get(f"{lang}_cap", text)
        chunks = chunk_words(cap_text, max_chars)
        cap_words = words if cap_text == text else None
        for (s0, s1), c in zip(caption_times(chunks, dur, cap_words), chunks):
            caps.append({"text": " ".join(c), "start": round(at + s0, 3), "end": round(at + s1 + 0.12, 3)})
        status = "OK" if dur <= limit else "OVERRUN"
        report.append(f"{status} seg{i + 1} at={at:.2f}s dur={dur:.2f}s limit={limit:.2f}s speed={speed:.2f}")
    # субтитры не перекрываются: конец фразы <= начала следующей, всё внутри [0, duration_s];
    # при OVERRUN голос заходит на следующий якорь — такие фразы схлопываются (start = end), видно по WARN
    for c in caps:
        c["start"], c["end"] = min(c["start"], total), min(c["end"], total)
    for p, q in zip(caps, caps[1:]):
        p["end"] = max(p["start"], min(p["end"], q["start"]))
    for c in caps:
        if c["end"] - c["start"] < 0.3:
            print(f"WARN субтитр «{c['text']}» {c['start']:.2f}–{c['end']:.2f} с — короче 0.3 с")
    peak = np.max(np.abs(track)) or 1.0
    track = track[: int(total * SR)] / peak * 0.89          # −1 дБFS
    os.makedirs(out_dir, exist_ok=True)
    sf.write(os.path.join(out_dir, f"vo_{lang}.wav"), track, SR, subtype="FLOAT")
    json.dump(caps, open(os.path.join(out_dir, f"captions_{lang}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n".join(report))
    print(f"TTS {lang}: {len(segs)} сегментов, {len(caps)} фраз субтитров -> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="озвучка + субтитры по script.json")
    ap.add_argument("script")
    ap.add_argument("lang")
    ap.add_argument("out_dir")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="длина строки субтитра (иначе script.caption_max_chars, иначе 26)")
    a = ap.parse_args()
    main(a.script, a.lang, a.out_dir, a.max_chars)
