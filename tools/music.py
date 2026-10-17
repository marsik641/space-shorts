"""Процедурная музыка и звуковой дизайн для ролика (без сторонних треков -> никаких Content ID).

    .venv/Scripts/python tools/music.py <cues.json> <out.wav>

cues.json (обязательно только duration_s; остальное — с умолчаниями, дающими звук ep001):
{
  "duration_s": 60.0, "seed": 1, "key": "A",        # key — тоника дрона и искр: C, C#, Db, … , Bb, B
  "chords": [[0, "Am9"], [8, "Fmaj7"], ...],        # смена гармонии (с, аккорд)
  "pulses": [0.53, 2.23, ...],                      # удары пульса — вспышки маяка в кадре (с), вне [0, T) — WARN
  "risers": [16.0, 28.0],                           # подъёмы к склейке (с — момент склейки); tc < length_s — WARN,
                                                    # tc > duration_s — хвост подъёма обрезается концом ролика
  "fade_out_s": 1.5,
  "layers": {"drone": 1, "pad": 1, "sparks": 1, "wind": 1, "pulse": 1, "riser": 1},  # множители слоёв
  "pad":    {"harmonics": 6, "rolloff": 1.6, "detune": 0.12, "attack": 2.5, "release": 3.0, "octave": -1},
  "sparks": {"mode": "minor", "every_s": 2.2, "octave": 1},     # или "scale": [0, 2, 4, 7, ...] (полутоны)
  "wind":   {"lo_hz": 120, "hi_hz": 900, "rate_hz": 0.07},
  "pulse":  {"freq_hz": 45, "sweep_hz": 25, "decay": 7.0, "click": 0.18, "length_s": 0.7},
  "riser":  {"length_s": 1.6},
  "reverb": {"seconds": 3.5, "mix": 0.4},
  "bpm": null,                                       # число — сетка: начала искр встают на долю/subdiv
  "grid": {"subdiv": 2, "offset_s": 0.0, "pulses": false},     # pulses: true — и удары на сетку (рвёт синхрон
}                                                               # с вспышками в кадре; по умолчанию нет)
Поля: harmonics — число гармоник «пилы» пэда, rolloff — показатель завала 1/h^rolloff (больше -> темнее),
detune — расстройка L/R в полутонах, attack/release — огибающая аккорда (с), octave — октава пэда от корня.
Лады искр (mode): minor, major, dorian, lydian. pulse: freq_hz — частота саба, sweep_hz — «удар» вниз по
частоте, decay — скорость затухания (1/с), click — громкость щелчка, length_s — длина удара.
reverb: seconds — время спада, mix — доля мокрого сигнала (0..1). Неизвестный ключ верхнего уровня — WARN
("note", "comment" и ключи на "_" допустимы). Правило: значения не копировать из прошлых эпизодов.

Аккорды: корень (C, C#, Db, D, D#, Eb, E, F, F#, Gb, G, G#, Ab, A, A#, Bb, B, а также Cb, Fb, E#, B#) +
качество: "" (мажор), m, 7, m7, maj7, 9, m9, maj9, 11 (без терции), m11, sus2, sus4, 7sus4, dim, dim7,
m7b5, aug, 6, m6, add9, madd9, maj7#11. Неизвестное качество или корень -> ValueError.

Слои: суб-дрон, пэд с медленной атакой (аддитивный синтез + мягкий фильтр), высокие «искры»,
шумовой «ветер», удары пульса (саб + щелчок), подъёмы-шумы к склейкам, общая реверберация.
Выход — стерео 48 кГц float. Сведение с голосом — tools/mix.py.
"""
import json
import sys

import numpy as np
import soundfile as sf

SR = 48000
NOTE = {"C": -9, "C#": -8, "Db": -8, "D": -7, "D#": -6, "Eb": -6, "E": -5, "Fb": -5, "E#": -4, "F": -4,
        "F#": -3, "Gb": -3, "G": -2, "G#": -1, "Ab": -1, "A": 0, "A#": 1, "Bb": 1, "B": 2, "Cb": 2, "B#": -9}
CHORDS = {   # интервалы в полутонах от корня
    "": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11),
    "9": (0, 4, 7, 10, 14), "m9": (0, 3, 7, 10, 14), "maj9": (0, 4, 7, 11, 14),
    "11": (0, 7, 10, 14, 17), "m11": (0, 3, 7, 10, 14, 17),
    "sus2": (0, 2, 7), "sus4": (0, 5, 7), "7sus4": (0, 5, 7, 10),
    "dim": (0, 3, 6), "dim7": (0, 3, 6, 9), "m7b5": (0, 3, 6, 10), "aug": (0, 4, 8),
    "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9), "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14),
    "maj7#11": (0, 4, 7, 11, 18),
}
MODES = {    # ступени искр (полутоны от тоники): характерные тоны лада + октава
    "minor": (0, 2, 3, 7, 10, 12, 14, 15, 19),
    "major": (0, 2, 4, 7, 11, 12, 14, 16, 19),
    "dorian": (0, 2, 3, 7, 9, 10, 12, 14, 15, 19),
    "lydian": (0, 2, 4, 6, 7, 11, 12, 14, 16, 18, 19),
}
DEFAULTS = {
    "layers": {"drone": 1.0, "pad": 1.0, "sparks": 1.0, "wind": 1.0, "pulse": 1.0, "riser": 1.0},
    "pad": {"harmonics": 6, "rolloff": 1.6, "detune": 0.12, "attack": 2.5, "release": 3.0, "octave": -1},
    "sparks": {"mode": "minor", "every_s": 2.2, "octave": 1, "scale": None},
    "wind": {"lo_hz": 120.0, "hi_hz": 900.0, "rate_hz": 0.07},
    "pulse": {"freq_hz": 45.0, "sweep_hz": 25.0, "decay": 7.0, "click": 0.18, "length_s": 0.7},
    "riser": {"length_s": 1.6},
    "reverb": {"seconds": 3.5, "mix": 0.4},
    "grid": {"subdiv": 2, "offset_s": 0.0, "pulses": False},
}
TOP_KEYS = {"duration_s", "seed", "key", "chords", "pulses", "risers", "fade_out_s", "bpm", "note", "comment",
            *DEFAULTS}


def hz(semi_from_a4):
    return 440.0 * 2 ** (semi_from_a4 / 12.0)


def parse_root(name):
    """'Bb7' -> ('Bb', '7'); неизвестный корень -> ValueError."""
    root = name[:2] if len(name) > 1 and name[1] in "#b" else name[:1]
    if root not in NOTE:
        raise ValueError(f"неизвестный корень: {name!r}")
    return root, name[len(root):]


def parse_chord(name):
    """'Am9' -> (полутоны корня от A4, интервалы); неизвестное качество -> ValueError (без подмены мажором)."""
    root, q = parse_root(name)
    if q not in CHORDS:
        raise ValueError(f"неизвестный аккорд {name!r}: качество {q!r}; есть: {', '.join(k or '(мажор)' for k in CHORDS)}")
    return NOTE[root], CHORDS[q]


def opts(cues, group):
    """Параметры группы: умолчания + заданное в cues; неизвестный ключ группы -> ValueError."""
    got = cues.get(group) or {}
    bad = set(got) - set(DEFAULTS[group])
    if bad:
        raise ValueError(f"{group}: неизвестные ключи {sorted(bad)}; есть {sorted(DEFAULTS[group])}")
    return {**DEFAULTS[group], **got}


def fft_filter(x, lo=None, hi=None, slope=2.0):
    """Мягкий полосовой фильтр в частотной области (весь сигнал целиком)."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1.0 / SR)
    g = np.ones_like(f)
    if hi:
        g *= 1.0 / (1.0 + (f / hi) ** (2 * slope))
    if lo:
        g *= 1.0 / (1.0 + (lo / np.maximum(f, 1e-3)) ** (2 * slope))
    if X.ndim > 1:
        g = g[:, None]
    return np.fft.irfft(X * g, n=x.shape[0], axis=0)


def reverb(x, seconds=3.2, mix=0.35, seed=0):
    """Свёрточная реверберация: экспоненциально затухающий стерео-шум (большой «зал»)."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9 * t / seconds)
    ir = rng.standard_normal((n, 2)) * env[:, None]
    ir = fft_filter(ir, hi=6000, slope=1.0)
    ir /= np.sqrt((ir ** 2).sum(axis=0, keepdims=True))
    N = x.shape[0] + n
    nfft = 1 << (N - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft, axis=0) * np.fft.rfft(ir, nfft, axis=0), nfft, axis=0)[: x.shape[0]]
    return (1 - mix) * x + mix * y


def envelope(t, a, r, t0, t1):
    """Плавная огибающая ноты: атака a, затухание r, звучит на [t0, t1]."""
    e = np.clip((t - t0) / a, 0, 1) * np.clip((t1 + r - t) / r, 0, 1)
    return e * e * (3 - 2 * e)


def build(cues):
    for k in cues:
        if k not in TOP_KEYS and not k.startswith("_"):
            print(f"WARN cues: неизвестный ключ {k!r} — игнорирую")
    T = cues["duration_s"]
    n = int(T * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(cues.get("seed", 1))
    out = np.zeros((n, 2))
    lay = opts(cues, "layers")
    pad, spk, wnd = opts(cues, "pad"), opts(cues, "sparks"), opts(cues, "wind")
    pul, ris, rev, grid = opts(cues, "pulse"), opts(cues, "riser"), opts(cues, "reverb"), opts(cues, "grid")
    bpm = cues.get("bpm")
    if pad["harmonics"] < 1 or pad["attack"] <= 0 or pad["release"] <= 0:
        raise ValueError(f"pad: harmonics ≥ 1, attack/release > 0: {pad}")
    if not 0 <= rev["mix"] <= 1 or rev["seconds"] <= 0:
        raise ValueError(f"reverb: seconds > 0, mix 0..1: {rev}")
    if bpm is not None and (bpm <= 0 or grid["subdiv"] < 1):
        raise ValueError(f"bpm > 0 и grid.subdiv ≥ 1: bpm={bpm}, grid={grid}")
    step = 60.0 / bpm / grid["subdiv"] if bpm else None

    def snap(x):
        return grid["offset_s"] + round((x - grid["offset_s"]) / step) * step if step else x

    # 1. суб-дрон: тоника и квинта, медленная пульсация
    key = NOTE[parse_root(cues.get("key", "A"))[0]]
    for semi, amp in ((key - 36, 0.20), (key - 29, 0.10)):
        f = hz(semi)
        lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.05 * t + rng.uniform(0, 6))
        s = np.sin(2 * np.pi * f * t) * lfo * amp * lay["drone"]
        out += s[:, None]

    # 2. пэд: аккорды, аддитивные «пилы» с завалом гармоник, расстройка по каналам
    chords = cues.get("chords", [[0, "Am9"]])
    parsed = [parse_chord(name) for _, name in chords]      # все ошибки аккордов — до синтеза
    for i, (t0, name) in enumerate(chords):
        t1 = chords[i + 1][0] if i + 1 < len(chords) else T
        root, ivals = parsed[i]
        env = envelope(t, pad["attack"], pad["release"], t0, t1)
        idx = np.where(env > 0)[0]
        if len(idx) == 0:
            continue
        tt = t[idx]
        for iv in ivals:
            f0 = hz(root + 12 * pad["octave"] + iv)
            for ch, det in ((0, -pad["detune"]), (1, pad["detune"])):
                fr = f0 * 2 ** (det / 12.0)
                v = np.zeros_like(tt)
                for h in range(1, int(pad["harmonics"]) + 1):
                    v += np.sin(2 * np.pi * fr * h * tt + rng.uniform(0, 6)) / h ** pad["rolloff"]
                out[idx, ch] += v * env[idx] * 0.035 * lay["pad"]

    # 3. искры: высокие тоны лада, редкие и тихие
    if spk["scale"]:
        scale = tuple(spk["scale"])
    elif spk["mode"] in MODES:
        scale = MODES[spk["mode"]]
    else:
        raise ValueError(f"sparks.mode {spk['mode']!r}: есть {sorted(MODES)}")
    for _ in range(int(T / spk["every_s"])):
        t0 = rng.uniform(0, T - 3)
        if step:
            t0 = min(max(0.0, snap(t0)), T - 3)
        f = hz(key + 12 * spk["octave"] + scale[rng.integers(len(scale))])
        dur = rng.uniform(1.5, 3.5)
        env = envelope(t, 0.4, dur, t0, t0 + 0.2) * 0.022 * lay["sparks"]
        pan = rng.uniform(0.2, 0.8)
        s = np.sin(2 * np.pi * f * t) * env
        out[:, 0] += s * (1 - pan)
        out[:, 1] += s * pan

    # 4. «ветер»: шум в полосе, медленно дышит
    wind = fft_filter(rng.standard_normal((n, 2)), lo=wnd["lo_hz"], hi=wnd["hi_hz"], slope=1.5)
    wind /= np.abs(wind).max()
    breath = 0.55 + 0.45 * np.sin(2 * np.pi * wnd["rate_hz"] * t)[:, None]
    out += wind * breath * 0.05 * lay["wind"]

    # 5. удары пульса: саб + щелчок (каждый проход луча через «наблюдателя»)
    for tp in cues.get("pulses", []):
        if step and grid["pulses"]:
            tp = snap(tp)
        a = int(tp * SR)
        if a >= n or tp < 0:
            print(f"WARN pulse {tp} с вне [0, {T}) — пропущен")
            continue
        L = min(int(pul["length_s"] * SR), n - a)
        tt = np.arange(L) / SR
        thump = (np.sin(2 * np.pi * (pul["freq_hz"] + pul["sweep_hz"] * np.exp(-tt * 18)) * tt)
                 * np.exp(-tt * pul["decay"]) * 0.55)
        click = rng.standard_normal(L) * np.exp(-tt * 300.0) * pul["click"]
        click = fft_filter(click[:, None], lo=1500, hi=9000)[:, 0]
        out[a:a + L] += ((thump + click) * lay["pulse"])[:, None]

    # 6. подъёмы к склейкам: шум с растущей огибающей и сдвигом полосы; хвост за концом ролика обрезается
    for tc in cues.get("risers", []):
        L = int(ris["length_s"] * SR)
        a = int(tc * SR) - L
        if a < 0 or a >= n:
            print(f"WARN riser {tc} с вне [{ris['length_s']}, {T} + {ris['length_s']}) — пропущен")
            continue
        tt = np.arange(L) / L
        r = fft_filter(rng.standard_normal((L, 2)), lo=800, hi=7000) * (tt ** 2.2)[:, None]
        r /= np.abs(r).max()
        m = min(L, n - a)
        out[a:a + m] += r[:m] * 0.10 * lay["riser"]

    out = reverb(out, seconds=rev["seconds"], mix=rev["mix"], seed=cues.get("seed", 1))
    fo = cues.get("fade_out_s", 1.5)
    if fo:
        out[-int(fo * SR):] *= np.linspace(1, 0, int(fo * SR))[:, None]
    fi = int(0.05 * SR)
    out[:fi] *= np.linspace(0, 1, fi)[:, None]
    peak = np.abs(out).max()
    if peak == 0:
        raise ValueError("тишина: все слои выключены")
    return (out / peak * 0.89).astype(np.float32)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    cues = json.load(open(sys.argv[1], encoding="utf-8"))
    sf.write(sys.argv[2], build(cues), SR, subtype="FLOAT")
    print("MUSIC", sys.argv[2], cues["duration_s"], "s")
