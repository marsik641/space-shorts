"""Сведение: голос + музыка с автодакингом -> стерео WAV 48 кГц, громкость под YouTube (−14 LUFS, ≤ −1 dBTP).

    .venv/Scripts/python tools/mix.py <vo.wav> <music.wav> <out.wav> [--music-db -20] [--duck-db -9] [--lufs -14]
                                      [--ceiling -1] [--no-tp]

Входы — любой частоты дискретизации (приводятся к 48 кГц через resample_poly), моно или стерео.
Лимитер (limit): упреждение 5 мс, атака — минимум по окну упреждения + сглаживание двумя скользящими
средними (линейно-гладкий спад усиления, без ступенек в один сэмпл), отпускание — удержание пика + экспонента.
Потолок по умолчанию считается в true-peak (детекция по 4× передискретизации, BS.1770): после AAC межсэмпловые
пики не уходят за 0 dBTP. Если итоговый true-peak всё же выше потолка, потолок понижается на превышение и
лимитер прогоняется ещё раз (до 3 раз). --no-tp — старое поведение (потолок по сэмплам).
"""
import argparse
from math import gcd

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.ndimage import maximum_filter1d, minimum_filter1d
from scipy.signal import resample_poly

SR = 48000
OS = 4          # передискретизация для true-peak


def db(x):
    return 10 ** (x / 20.0)


def to_sr(x, sr_in, sr_out=SR):
    """Передискретизация полифазным фильтром (с подавлением зеркальных образов), ось 0 — время."""
    if sr_in == sr_out:
        return x
    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(x, sr_out // g, sr_in // g, axis=0).astype(np.float32)


def to_stereo(x):
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    if x.shape[1] > 2:
        raise ValueError(f"ожидается моно или стерео, получено {x.shape[1]} каналов")
    return x


def true_peak_env(x):
    """Пик по 4× передискретизации на каждый исходный сэмпл (максимум по каналам и по 4 фазам)."""
    up = np.abs(resample_poly(x, OS, 1, axis=0))
    up = up[: len(x) * OS].reshape(len(x), OS, -1)
    return up.max(axis=(1, 2))


def true_peak_db(x):
    return 20 * np.log10(max(true_peak_env(x).max(), 1e-12))


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


def _min_fwd(a, L):
    """m[n] = min(a[n .. n+L-1]); за концом сигнала — 1 (ослабление не нужно)."""
    h = L // 2
    L = 2 * h + 1
    p = np.concatenate([a, np.ones(2 * h)])
    return minimum_filter1d(p, size=L, mode="nearest")[h: h + len(a)]


def _max_back(a, L):
    """m[n] = max(a[n-L+1 .. n]); до начала сигнала — 0."""
    h = L // 2
    L = 2 * h + 1
    p = np.concatenate([np.zeros(2 * h), a])
    return maximum_filter1d(p, size=L, mode="nearest")[h: h + len(a)]


def _mean_back(a, L):
    """s[n] = mean(a[n-L+1 .. n]); до начала сигнала — a[0]."""
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([np.full(L - 1, a[0]), a]))])
    return (c[L:] - c[:-L]) / L


def _peak_decay(d, r, blk=1024):
    """y[n] = max(d[n], r·y[n-1]) — пиковый детектор с экспоненциальным спадом (векторно по блокам)."""
    y = np.empty_like(d)
    prev = 0.0
    k = np.arange(blk)
    rk = r ** k
    for i in range(0, len(d), blk):
        seg = d[i:i + blk]
        m = len(seg)
        acc = np.maximum.accumulate(seg / rk[:m]) * rk[:m]
        out = np.maximum(acc, prev * r * rk[:m])
        y[i:i + m] = out
        prev = out[-1]
    return y


def limit(x, ceiling, lookahead_s=0.005, release_s=0.08, hold_s=None, tp=True):
    """Пиковый лимитер с упреждением; возвращает x·g. Гарантия: g[n] ≤ need[n] = ceiling/пик[n].

    need -> минимум по окну упреждения [n, n+L) -> две скользящие средние (L1+L2−1 = L) по прошлому.
    Каждое усреднённое значение берётся из окон, содержащих n, поэтому g ≤ need, а спад к нужному
    уровню начинается за L сэмплов до пика и идёт гладко (шаг ≤ глубина/L1 на сэмпл).
    Отпускание: глубина ослабления 1−g держится hold_s (по умолчанию = упреждению), затем экспонента release_s.
    tp=True — пик считается по 4× передискретизации (true-peak), иначе по сэмплам."""
    peak = true_peak_env(x) if tp else np.abs(x).max(axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    L = max(3, int(lookahead_s * SR))
    L1 = (L + 1) // 2
    L2 = L - L1 + 1
    g = _mean_back(_mean_back(_min_fwd(need, L), L1), L2)
    depth = _max_back(1.0 - g, max(1, int((lookahead_s if hold_s is None else hold_s) * SR)))
    depth = _peak_decay(depth, np.exp(-1.0 / (release_s * SR)))
    g = np.minimum(1.0 - depth, need)   # страховка от ошибки округления cumsum (~1e-12), ступенек не даёт
    return x * g[:, None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vo")
    ap.add_argument("music")
    ap.add_argument("out")
    ap.add_argument("--music-db", type=float, default=-20.0, help="уровень музыки относительно голоса без дакинга")
    ap.add_argument("--duck-db", type=float, default=-9.0, help="дополнительное ослабление музыки под голосом")
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--ceiling", type=float, default=-1.0, help="потолок пика, dBTP (dBFS при --no-tp)")
    ap.add_argument("--no-tp", action="store_true", help="потолок по сэмплам, без true-peak")
    ap.add_argument("--max-seconds", type=float, default=None,
                    help="обрезать итог до этой длины с затуханием 30 мс (AAC добавляет ~10 мс заполнения: "
                         "для ролика 60.0 с давать 59.97, чтобы дорожка в MP4 не вышла за 60.0)")
    a = ap.parse_args()
    tp = not a.no_tp

    vo, sr1 = sf.read(a.vo, dtype="float32")
    mu, sr2 = sf.read(a.music, dtype="float32")
    for name, sr in ((a.vo, sr1), (a.music, sr2)):
        if sr != SR:
            print(f"WARN {name}: {sr} Гц -> {SR} Гц (resample_poly)")
    vo = to_stereo(to_sr(vo, sr1))
    mu = to_stereo(to_sr(mu, sr2))
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
    base = vo + mu * gain[:, None]

    # громкость к цели + лимитер; 3 итерации — лимитер чуть съедает громкость.
    # Если true-peak итога выше потолка (межсэмпловые пики после гейна), потолок лимитера понижается.
    ceil_db = a.ceiling
    for _ in range(3):
        mix = base
        for _ in range(3):
            mix = mix * db(a.lufs - meter.integrated_loudness(mix))
            mix = limit(mix, ceiling=db(ceil_db), tp=tp)
        pk = true_peak_db(mix) if tp else 20 * np.log10(np.abs(mix).max())
        if pk <= a.ceiling + 1e-3:
            break
        ceil_db -= pk - a.ceiling + 0.05
        print(f"WARN пик {pk:.2f} > {a.ceiling:.1f}: потолок лимитера -> {ceil_db:.2f}")
    if a.max_seconds is not None and len(mix) > int(a.max_seconds * SR):
        mix = mix[: int(a.max_seconds * SR)].copy()
        nf = int(0.03 * SR)
        mix[-nf:] *= np.linspace(1.0, 0.0, nf)[:, None]
        n = len(mix)
    final = meter.integrated_loudness(mix)
    sf.write(a.out, mix.astype(np.float32), SR, subtype="PCM_24")
    print(f"MIX {a.out}: {final:.1f} LUFS, peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS, "
          f"true-peak {true_peak_db(mix):.1f} dBTP, {n / SR:.2f} s")


if __name__ == "__main__":
    main()
