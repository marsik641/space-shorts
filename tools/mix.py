"""Сведение: голос + музыка с автодакингом -> стерео WAV, громкость под YouTube (−14 LUFS, пик ≤ −1 dBFS).

    .venv/Scripts/python tools/mix.py <vo.wav> <music.wav> <out.wav> [--music-db -20] [--duck-db -9] [--lufs -14]
"""
import argparse

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

SR = 48000


def db(x):
    return 10 ** (x / 20.0)


def smooth_env(x, attack_s, release_s):
    """Огибающая с раздельными атакой/спадом (по блокам 10 мс — быстро и достаточно гладко)."""
    blk = int(0.01 * SR)
    nb = int(np.ceil(len(x) / blk))
    pad = np.zeros(nb * blk)
    pad[: len(x)] = np.abs(x)
    lvl = np.sqrt((pad.reshape(nb, blk) ** 2).mean(axis=1))
    a = np.exp(-0.01 / attack_s)
    r = np.exp(-0.01 / release_s)
    env = np.zeros(nb)
    e = 0.0
    for i, v in enumerate(lvl):
        c = a if v > e else r
        e = c * e + (1 - c) * v
        env[i] = e
    return np.repeat(env, blk)[: len(x)]


def limit(x, ceiling, lookahead_s=0.005, release_s=0.08):
    """Пиковый лимитер: требуемое ослабление -> минимум по окну упреждения -> плавный спад."""
    from scipy.ndimage import minimum_filter1d
    need = np.minimum(1.0, ceiling / np.maximum(np.abs(x).max(axis=1), 1e-9))
    la = max(1, int(lookahead_s * SR))
    g = minimum_filter1d(need, size=2 * la + 1, mode="nearest")
    # спад (возврат к 1) — экспоненциальный, атака мгновенная (упреждение уже учтено окном)
    r = np.exp(-1.0 / (release_s * SR))
    from scipy.signal import lfilter
    rev = 1.0 - g                                   # глубина ослабления
    # пиковый детектор с затуханием: y = max(x, r*y_prev)
    blk = 1024
    y = np.empty_like(rev)
    prev = 0.0
    for i in range(0, len(rev), blk):
        seg = rev[i:i + blk]
        # внутри блока — честная рекурсия через накопленный максимум с затуханием
        k = np.arange(len(seg))
        dec = prev * r ** (k + 1)
        acc = np.maximum.accumulate(seg / r ** k) * r ** k
        out = np.maximum(acc, dec)
        y[i:i + blk] = out
        prev = out[-1]
    g = 1.0 - lfilter([1 - np.exp(-1.0 / (0.002 * SR))], [1, -np.exp(-1.0 / (0.002 * SR))], y)
    g = np.minimum(g, minimum_filter1d(need, size=2 * la + 1, mode="nearest"))
    return x * g[:, None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vo")
    ap.add_argument("music")
    ap.add_argument("out")
    ap.add_argument("--music-db", type=float, default=-20.0, help="уровень музыки относительно голоса без дакинга")
    ap.add_argument("--duck-db", type=float, default=-9.0, help="дополнительное ослабление музыки под голосом")
    ap.add_argument("--lufs", type=float, default=-14.0)
    a = ap.parse_args()

    vo, sr1 = sf.read(a.vo, dtype="float32")
    mu, sr2 = sf.read(a.music, dtype="float32")
    assert sr1 == SR and sr2 == SR, "ожидается 48 кГц"
    if vo.ndim == 1:
        vo = np.stack([vo, vo], axis=1)
    n = max(len(vo), len(mu))
    vo = np.pad(vo, ((0, n - len(vo)), (0, 0)))
    mu = np.pad(mu, ((0, n - len(mu)), (0, 0)))

    meter = pyln.Meter(SR)
    vo_l = meter.integrated_loudness(vo)
    mu_l = meter.integrated_loudness(mu)
    mu = mu * db((vo_l + a.music_db) - mu_l)
    # дакинг: музыка проседает, пока звучит голос
    env = smooth_env(vo.mean(axis=1), attack_s=0.06, release_s=0.45)
    active = np.clip(env / (env.max() * 0.08 + 1e-9), 0, 1)
    gain = db(a.duck_db * active)
    mix = vo + mu * gain[:, None]

    # громкость к цели + лимитер с упреждением (пик ≤ −1 dBFS); 3 итерации — лимитер чуть съедает громкость
    for _ in range(3):
        mix = mix * db(a.lufs - meter.integrated_loudness(mix))
        mix = limit(mix, ceiling=db(-1.0))
    final = meter.integrated_loudness(mix)
    sf.write(a.out, mix.astype(np.float32), SR, subtype="PCM_24")
    print(f"MIX {a.out}: {final:.1f} LUFS, peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS, {n / SR:.2f} s")


if __name__ == "__main__":
    main()
