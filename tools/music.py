"""Процедурная музыка и звуковой дизайн для ролика (без сторонних треков -> никаких Content ID).

    .venv/Scripts/python tools/music.py <cues.json> <out.wav>

cues.json:
{
  "duration_s": 60.0, "seed": 1, "key": "A", "bpm_free": true,
  "chords": [[0, "Am9"], [8, "Fmaj7"], ...],      # смена гармонии (с)
  "pulses": [0.53, 2.23, ...],                       # «удары пульса» — вспышки маяка в кадре (с)
  "risers": [16.0, 28.0],                            # подъёмы в склейку (с — момент склейки)
  "fade_out_s": 1.5
}
Слои: суб-дрон, пэд с медленной атакой (аддитивный синтез + мягкий фильтр), высокие «искры»,
шумовой «ветер», удары пульса (саб 45 Гц + щелчок), подъёмы-шумы к склейкам, общая реверберация.
Выход — стерео 48 кГц float. Сведение с голосом — tools/mix.py.
"""
import json
import sys

import numpy as np
import soundfile as sf

SR = 48000
NOTE = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2, "G#": -1, "A": 0, "A#": 1, "B": 2}
CHORDS = {   # интервалы в полутонах от корня
    "m9": (0, 3, 7, 10, 14), "maj7": (0, 4, 7, 11), "maj9": (0, 4, 7, 11, 14), "6": (0, 4, 7, 9),
    "sus2": (0, 2, 7), "m7": (0, 3, 7, 10), "add9": (0, 4, 7, 14), "m": (0, 3, 7), "": (0, 4, 7),
}


def hz(semi_from_a4):
    return 440.0 * 2 ** (semi_from_a4 / 12.0)


def parse_chord(name):
    root = name[:2] if len(name) > 1 and name[1] == "#" else name[:1]
    q = name[len(root):]
    if q.startswith("m") and not q.startswith("maj"):
        q = "m" + q[1:] if q[1:] in ("9", "7", "") else q
    ivals = CHORDS.get(q, CHORDS[""])
    return NOTE[root], ivals


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
    T = cues["duration_s"]
    n = int(T * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(cues.get("seed", 1))
    out = np.zeros((n, 2))

    # 1. суб-дрон: тоника и квинта, медленная пульсация
    key = NOTE[cues.get("key", "A")]
    for semi, amp in ((key - 36, 0.20), (key - 29, 0.10)):
        f = hz(semi)
        lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.05 * t + rng.uniform(0, 6))
        s = np.sin(2 * np.pi * f * t) * lfo * amp
        out += s[:, None]

    # 2. пэд: аккорды, аддитивные «пилы» с завалом гармоник, расстройка по каналам
    chords = cues.get("chords", [[0, "Am9"]])
    for i, (t0, name) in enumerate(chords):
        t1 = chords[i + 1][0] if i + 1 < len(chords) else T
        root, ivals = parse_chord(name)
        env = envelope(t, 2.5, 3.0, t0, t1)
        idx = np.where(env > 0)[0]
        if len(idx) == 0:
            continue
        tt = t[idx]
        for iv in ivals:
            f0 = hz(root - 12 + iv)
            for ch, det in ((0, -0.12), (1, 0.12)):
                fr = f0 * 2 ** (det / 12.0)
                v = np.zeros_like(tt)
                for h in range(1, 7):
                    v += np.sin(2 * np.pi * fr * h * tt + rng.uniform(0, 6)) / h ** 1.6
                out[idx, ch] += v * env[idx] * 0.035

    # 3. искры: высокие тоны лада, редкие и тихие
    scale = (0, 2, 3, 7, 10, 12, 14, 15, 19)
    for _ in range(int(T / 2.2)):
        t0 = rng.uniform(0, T - 3)
        f = hz(key + 12 + scale[rng.integers(len(scale))])
        dur = rng.uniform(1.5, 3.5)
        env = envelope(t, 0.4, dur, t0, t0 + 0.2) * 0.022
        pan = rng.uniform(0.2, 0.8)
        s = np.sin(2 * np.pi * f * t) * env
        out[:, 0] += s * (1 - pan)
        out[:, 1] += s * pan

    # 4. «ветер»: шум в полосе, медленно дышит
    wind = fft_filter(rng.standard_normal((n, 2)), lo=120, hi=900, slope=1.5)
    wind /= np.abs(wind).max()
    breath = 0.55 + 0.45 * np.sin(2 * np.pi * 0.07 * t)[:, None]
    out += wind * breath * 0.05

    # 5. удары пульса: саб + щелчок (каждый проход луча через «наблюдателя»)
    for tp in cues.get("pulses", []):
        a = int(tp * SR)
        L = int(0.7 * SR)
        if a >= n:
            continue
        L = min(L, n - a)
        tt = np.arange(L) / SR
        thump = np.sin(2 * np.pi * (45 + 25 * np.exp(-tt * 18)) * tt) * np.exp(-tt * 7.0) * 0.55
        click = rng.standard_normal(L) * np.exp(-tt * 300.0) * 0.18
        click = fft_filter(click[:, None], lo=1500, hi=9000)[:, 0]
        out[a:a + L] += (thump + click)[:, None]

    # 6. подъёмы к склейкам: шум с растущей огибающей и сдвигом полосы
    for tc in cues.get("risers", []):
        L = int(1.6 * SR)
        a = int(tc * SR) - L
        if a < 0:
            continue
        tt = np.arange(L) / L
        r = fft_filter(rng.standard_normal((L, 2)), lo=800, hi=7000) * (tt ** 2.2)[:, None]
        r /= np.abs(r).max()
        out[a:a + L] += r * 0.10

    out = reverb(out, seconds=3.5, mix=0.4, seed=cues.get("seed", 1))
    fo = cues.get("fade_out_s", 1.5)
    if fo:
        out[-int(fo * SR):] *= np.linspace(1, 0, int(fo * SR))[:, None]
    fi = int(0.05 * SR)
    out[:fi] *= np.linspace(0, 1, fi)[:, None]
    return (out / np.abs(out).max() * 0.89).astype(np.float32)


if __name__ == "__main__":
    cues = json.load(open(sys.argv[1], encoding="utf-8"))
    sf.write(sys.argv[2], build(cues), SR, subtype="FLOAT")
    print("MUSIC", sys.argv[2], cues["duration_s"], "s")
