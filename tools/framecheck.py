"""Проверка PNG-секвенций эпизода до сборки MP4: целость кадров и разовые сбои рендера по скачкам размера файла.

    python tools/framecheck.py episodes/<id>/episode.json [--shots v1,v2] [--frames DIR] [--logs DIR]
                               [--thr 0.02] [--k 6] [--win 10] [--near 3] [--near-flash 15]

Кадры — <frames_dir>/<шот>/####.png (frames_dir из episode.json, по умолчанию out/<id>/<fmt>/frames; --frames —
другая папка с теми же подпапками шотов), номера — edit[].first .. first+frames−1 (first по умолчанию 1).
1. Целость: кадр есть, не пустой, сигнатура PNG, IHDR = format.w×h, файл кончается чанком IEND.
2. Сбой рендера — скачок размера файла между соседними кадрами. Шаг f = (size[f] − size[f−1]) / size[f−1];
   скачок — |шаг| > --thr (2 %) и > --k (6) × медиана |шагов| в окне ±--win (10) кадров. Ep002: на rinat-pc
   31 кадр v1 (135–165) вышел с другим светом антенны — в логе ошибок нет, время кадра обычное, а размер PNG
   прыгнул на −4,7 % / +5,2 % при фоне ±0,1 %. Скачки разного знака подряд — блок «вход/выход»: вход 135,
   выход 166 → перерендерить 135–165.
3. Задуманные события: скачок в пределах ±--near (3) кадров от EVENT шота или ±--near-flash (15) от FLASH —
   «событие», не ошибка (ep002: «восход» v2 EVENT 27 → скачки 26–28 до +40 %). FLASH — только пик гауссианы
   луча, а рампа размера идёт и на подъёме/спаде: в ep001 скачки 2–3 % в 10–12 кадрах от пика. Строки берутся
   как в tools/cues.py: out/logs/<id>/render_<шот>.log, запасной — превью; --logs DIR — своя папка.
Итог — последняя строка PASS (код 0) или FAIL (код 1): нет/битые кадры или скачки вне событий. Чинить: удалить
кадры блока (здесь, а при рендере на rinat-pc и там) и докачать рендер (готовые кадры пропускаются), повторить.
Только стандартная библиотека, без Blender: читает 24 байта начала и 12 конца файла, ~1 с на ролик.
"""
import argparse
import json
import os
import statistics
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_edit import ep_paths  # noqa: E402
from cues import find_log  # noqa: E402

SIG = b"\x89PNG\r\n\x1a\n"
IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def R(path):
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def pct(d, nd=1):
    """0.047 -> '+4,7 %', -0.047 -> '−4,7 %'."""
    return f"{d * 100:+.{nd}f} %".replace(".", ",").replace("-", "−")


def spans(fs):
    """[135, 136, 137, 140] -> '135–137, 140'."""
    out, fs = [], sorted(fs)
    for i, f in enumerate(fs):
        if i and f == fs[i - 1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in out)


def scan(path, w, h):
    """-> (размер, None) для целого кадра, иначе (размер | None, что не так)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, "нет"
    if size < 57:                                        # сигнатура + IHDR + IEND = 45 байт, без IDAT не кадр
        return size, "пустой" if size == 0 else f"{size} байт"
    with open(path, "rb") as fh:
        head = fh.read(24)
        fh.seek(-12, 2)
        tail = fh.read()
    if head[:8] != SIG or head[12:16] != b"IHDR":
        return size, "не PNG"
    pw, ph = int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if (pw, ph) != (w, h):
        return size, f"{pw}×{ph} вместо {w}×{h}"
    if tail != IEND:
        return size, "обрезан (нет IEND)"
    return size, None


def need_frames(edit, shots=None):
    """{шот: [кадры]} — объединение first..first+frames−1 по всем вхождениям шота в edit."""
    need = {}
    for s in edit:
        first = s.get("first", 1)
        need.setdefault(s["shot"], set()).update(range(first, first + s["frames"]))
    return {k: sorted(v) for k, v in need.items() if not shots or k in shots}


def steps(sizes):
    """{кадр: байты} -> {f: шаг f−1→f} — только между соседними целыми кадрами."""
    return {f: (sizes[f] - sizes[f - 1]) / sizes[f - 1] for f in sorted(sizes) if f - 1 in sizes}


def jumps(st, thr, k, win):
    """-> [(f, шаг, фон)]: |шаг| > thr и > k × фон, фон — медиана |шагов| в окне ±win (у краёв шота окно сдвигается)."""
    fs = sorted(st)
    n, size = len(fs), 2 * win + 1
    out = []
    for i, f in enumerate(fs):
        d = st[f]
        if abs(d) <= thr:
            continue
        lo = max(0, min(i - win, n - size))
        bg = statistics.median(abs(st[g]) for g in fs[lo:lo + size])
        if abs(d) > k * bg:
            out.append((f, d, bg))
    return out


def event_marks(flash, events, near, near_flash):
    """-> [(кадр, 'FLASH' | 'EVENT <имя>', радиус)] из строк лога шота."""
    out = [(f, "FLASH", near_flash) for f, _ in flash or []]
    for name, pairs in events.items():
        out += [(f, f"EVENT {name}", near) for f, _ in pairs]
    return out


def classify(jl, marks):
    """Скачки -> (события {(кадр, имя): [скачки]}, блоки [(вход, выход | None)])."""
    evs, rest = {}, []
    for j in jl:
        hit = min(((abs(j[0] - e), e, nm) for e, nm, r in marks if abs(j[0] - e) <= r), default=None)
        if hit:
            evs.setdefault((hit[1], hit[2]), []).append(j)
        else:
            rest.append(j)
    blocks, open_ = [], None                             # вход и выход — скачки разного знака подряд
    for j in rest:
        if open_ is None:
            open_ = j
        elif (j[1] > 0) != (open_[1] > 0):
            blocks.append((open_, j))
            open_ = None
        else:
            blocks.append((open_, None))
            open_ = j
    if open_:
        blocks.append((open_, None))
    return evs, blocks


def check_shot(shot, frames, d, w, h, marks, a):
    """-> (строки отчёта, {кадры к перерендеру}, [варианты для скачков без пары], [события 'шот a–b'])."""
    sizes, bad = {}, {}
    for f in frames:
        size, why = scan(os.path.join(d, f"{f:04d}.png"), w, h)
        if why:
            bad.setdefault(why, []).append(f)
        else:
            sizes[f] = size
    st = steps(sizes)
    evs, blocks = classify(jumps(st, a.thr, a.k, a.win), marks)
    lines, redo, alt, ev_spans = [], set(), [], []
    for why, fs in bad.items():
        lines.append(f"  {why}: {spans(fs)} ({len(fs)})")
        redo.update(fs)
    for (j_in, j_out) in blocks:
        f0 = j_in[0]
        if j_out:
            f1 = j_out[0] - 1
            n = f1 - f0 + 1
            lines.append(f"  СБОЙ {spans(range(f0, f1 + 1))} ({n} кадр.): вход {f0} {pct(j_in[1])}, "
                         f"выход {j_out[0]} {pct(j_out[1])} (фон {pct(j_in[2], 2)[1:]})")
            redo.update(range(f0, f1 + 1))
        else:                                            # сбой с края шота: какая сторона битая — видно глазами
            v = f"{f0}–{frames[-1]} или {frames[0]}–{f0 - 1}"
            lines.append(f"  СКАЧОК {f0} {pct(j_in[1])} без пары (фон {pct(j_in[2], 2)[1:]}): сбой {v} — "
                         f"сравнить кадры {f0 - 1} и {f0} глазами")
            alt.append(v)
    for (e, nm), jl in sorted(evs.items()):
        fs = [j[0] for j in jl]
        lines.append(f"  событие {spans(fs)} у {nm} {e}: " + ", ".join(f"{f} {pct(dd)}" for f, dd, _ in jl))
        ev_spans.append(f"{shot} {spans(fs)}")
    clean = [abs(v) for f, v in st.items() if not any(f == j[0] for jl in evs.values() for j in jl)]
    bg = statistics.median(clean) if clean else 0.0
    mx = max(((abs(v), f) for f, v in st.items()), default=(0.0, None))
    head = (f"{shot}: {len(sizes)}/{len(frames)} целых, фон |шаг| {pct(bg, 2)[1:]}, "
            f"макс {pct(mx[0])[1:]}" + (f" @ {mx[1]}" if mx[1] else ""))
    return [head] + lines, redo, alt, ev_spans


def main():
    for _s in (sys.stdout, sys.stderr):                  # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="PNG-секвенции эпизода: целость и скачки размера до сборки")
    ap.add_argument("episode")
    ap.add_argument("--shots", help="только эти шоты: v1,v2")
    ap.add_argument("--frames", help="папка с подпапками шотов (по умолчанию frames_dir эпизода)")
    ap.add_argument("--logs", help="папка с render_<шот>.log / prev_<шот>.log (FLASH/EVENT)")
    ap.add_argument("--thr", type=float, default=0.02, help="минимальный скачок, доля (0.02)")
    ap.add_argument("--k", type=float, default=6.0, help="скачок > k × медиана |шагов| в окне (6)")
    ap.add_argument("--win", type=int, default=10, help="окно медианы ±кадров (10)")
    ap.add_argument("--near", type=int, default=3, help="скачок ±кадров от EVENT — событие (3)")
    ap.add_argument("--near-flash", type=int, default=15, help="скачок ±кадров от FLASH — событие (15)")
    a = ap.parse_args()

    with open(a.episode, encoding="utf-8") as fh:
        ep = json.load(fh)
    fdir = a.frames or ep_paths(ep, a.episode)["frames_dir"]
    w, h = ep["format"]["w"], ep["format"]["h"]
    need = need_frames(ep["edit"], a.shots.split(",") if a.shots else None)
    if a.shots and set(a.shots.split(",")) - set(need):
        print("FAIL нет в edit:", ",".join(sorted(set(a.shots.split(",")) - set(need))))
        return 1
    total = sum(len(v) for v in need.values())
    print(f"FRAMECHECK {ep['id']}: {fdir}, {len(need)} шот., {total} кадров")
    redo, events = {}, []
    for shot, frames in need.items():
        log, flash, evs = find_log(ep, shot, a.logs)
        marks = event_marks(flash, evs, a.near, a.near_flash)
        lines, rr, alt, ev = check_shot(shot, frames, os.path.join(R(fdir), shot), w, h, marks, a)
        lines[0] += f"; FLASH/EVENT: {len(marks)} ({log or 'в логах нет'})"
        print("\n".join(lines))
        if rr or alt:
            redo[shot] = "; ".join(([spans(rr)] if rr else []) + alt)
        events += ev
    ev_txt = (f"; события: {', '.join(events[:8])}" + (f" … (+{len(events) - 8})" if len(events) > 8 else "")
              if events else "")
    if not redo:
        print(f"PASS: {total} кадров целы, скачков вне событий нет{ev_txt}")
        return 0
    for shot, txt in redo.items():
        print(f"RERENDER {shot}: {txt}")
    print(f"FAIL: битые кадры или сбои рендера в {len(redo)} шот. ({', '.join(redo)}){ev_txt}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
