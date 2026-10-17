"""Музыкальные cue по событиям рендера: FLASH/EVENT из логов -> pulses и risers в music_cues.json.

    python tools/cues.py episodes/<id>/episode.json [--thr 0.4] [--exclude v5:1-201 ...] [--logs DIR]
                         [--min-riser 2.0] [--events-to pulses|risers|none] [--dry-run]

Строки логов (печатает spacekit.shot; FLASH есть уже в превью — cue можно готовить до финала):
    FLASH <shot>: <кадр>:<яркость>, ...          — вспышки маяка (берутся с яркостью >= --thr)
    EVENT <shot> <name>: <кадр>[:<v>], ...       — прочие события (проход планеты, вспышка магнитара)
Лог шота: --logs DIR (render_<shot>.log, затем prev_<shot>.log), по умолчанию
out/logs/<id>/render_<shot>.log, запасной — out/<id>/<format_name>/logs/prev_<shot>.log.
Если в логе несколько строк для шота — берётся последняя.

Кадр шота -> секунды монтажа: t = (offset + f − first) / fps, где offset — начало шота в монтаже
(Σ frames предыдущих − Σ xfade_in предыдущих и текущего шота, как в assemble.py), first — edit[].first; кадры вне
first..first+frames−1 отбрасываются. Это та же конвенция, что в build_edit (кадр монтажа = round(t·fps) + 1).
(В ep001 pulses ставились как (offset + f)/fps — на 1 кадр позже.)
--exclude shot:a-b — выкинуть кадры шота a..b (вспышка перекрыта телом, key_pulse_flash этого не знает).
risers — моменты склеек не раньше --min-riser с от начала. Совпадающие (в пределах кадра) удары сливаются.
Пишет pulses и risers в music_cues.json (ep["music_cues"] или episodes/<id>/music_cues.json), остальные
поля (chords, key, seed, …) не трогает. --dry-run — только печать и сравнение с текущими значениями.
"""
import argparse
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RX_FLASH = re.compile(r"^FLASH\s+(\S+):\s*(.*)$")
RX_EVENT = re.compile(r"^EVENT\s+(\S+)\s+(\S+):\s*(.*)$")


def R(path):
    return path if os.path.isabs(path) else os.path.join(REPO, path)


def parse_pairs(text):
    """'32:0.99, 82:0.07' -> [(32, 0.99), (82, 0.07)]; '120, 340' -> [(120, None), (340, None)]."""
    out = []
    for tok in text.split(","):
        tok = tok.strip()
        if not tok:
            continue
        f, _, v = tok.partition(":")
        out.append((int(f), float(v) if v else None))
    return out


def parse_log(path, shot):
    """-> (flash [(f, v)] | None, events {name: [(f, v)]}) — последние строки для шота."""
    flash, events = None, {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            m = RX_FLASH.match(line)
            if m and m.group(1) == shot:
                flash = parse_pairs(m.group(2))
                continue
            m = RX_EVENT.match(line)
            if m and m.group(1) == shot:
                events[m.group(2)] = parse_pairs(m.group(3))
    return flash, events


def find_log(ep, shot, logs_dir):
    """-> (путь, flash, events): первый лог-кандидат, где есть FLASH/EVENT этого шота (финальный рендер
    ещё идёт — строки FLASH в его логе может не быть, тогда берётся превью)."""
    eid, fmt = ep["id"], ep.get("format_name", "9x16")
    if logs_dir:
        cands = [os.path.join(logs_dir, f"render_{shot}.log"), os.path.join(logs_dir, f"prev_{shot}.log")]
    else:
        cands = [f"out/logs/{eid}/render_{shot}.log", f"out/{eid}/{fmt}/logs/prev_{shot}.log"]
    for c in cands:
        if os.path.isfile(R(c)):
            flash, events = parse_log(R(c), shot)
            if flash is not None or events:
                return c, flash, events
    return None, None, {}


def parse_excludes(items):
    ex = {}
    for it in items or []:
        shot, _, rng = it.partition(":")
        a, _, b = rng.partition("-")
        ex.setdefault(shot, []).append((int(a), int(b or a)))
    return ex


def merge(times, eps):
    out = []
    for t in sorted(times):
        if not out or t - out[-1] > eps:
            out.append(t)
    return out


def build(ep, thr=0.4, excludes=None, logs_dir=None, min_riser=2.0, events_to="pulses", duration=None):
    fps = ep["format"]["fps"]
    excludes = excludes or {}
    pulses, risers, ev_times, src = [], [], {}, {}
    offset = 0
    for i, s in enumerate(ep["edit"]):
        shot, n, first = s["shot"], s["frames"], s.get("first", 1)
        if i:
            offset -= s.get("xfade_in", 0)
            if offset / fps >= min_riser:
                risers.append(round(offset / fps, 3))
        log, flash, events = find_log(ep, shot, logs_dir)
        src[shot] = log
        if not log:
            print(f"WARN {shot}: нет лога со строкой FLASH/EVENT {shot} (render_{shot}.log / prev_{shot}.log)")

        def keep(f):
            if not first <= f <= first + n - 1:
                return False
            return not any(a <= f <= b for a, b in excludes.get(shot, []))

        def t_of(f):
            return round((offset + f - first) / fps, 3)

        for f, v in flash or []:
            if v is not None and v >= thr and keep(f):
                pulses.append(t_of(f))
        for name, pairs in events.items():
            ts = [t_of(f) for f, _ in pairs if keep(f)]
            ev_times[f"{shot}/{name}"] = ts
            if events_to == "pulses":
                pulses += ts
            elif events_to == "risers":
                risers += ts
        offset += n
    if duration is not None:
        pulses = [t for t in pulses if 0 <= t < duration]
        risers = [t for t in risers if 0 < t <= duration]
    eps = 0.5 / fps
    return merge(pulses, eps), merge(risers, eps), ev_times, src


def compare(name, new, old, fps):
    """Печать сравнения со старыми значениями: max отклонение в кадрах, лишние/пропавшие."""
    if not old:
        print(f"  {name}: старых значений нет")
        return
    tol = 1.5 / fps
    dev = [min(abs(t - o) for o in old) for t in new]
    extra = [t for t, d in zip(new, dev) if d > tol]
    gone = [o for o in old if min((abs(t - o) for t in new), default=1e9) > tol]
    mx = round(max((d for d in dev if d <= tol), default=0.0) * fps)    # значения округлены до мс
    print(f"  {name}: новых {len(new)}, старых {len(old)}, совпали с точностью {mx} кадр(а); "
          f"лишние {extra}, пропали {gone}")


def main():
    for _s in (sys.stdout, sys.stderr):      # кириллица в консоли/пайпе Windows
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="FLASH/EVENT из логов рендера -> pulses/risers в music_cues.json")
    ap.add_argument("episode")
    ap.add_argument("--thr", type=float, default=0.4, help="порог яркости FLASH (0.4)")
    ap.add_argument("--exclude", action="append", metavar="SHOT:A-B", help="выкинуть кадры шота (повторяемый)")
    ap.add_argument("--logs", help="папка с render_<shot>.log / prev_<shot>.log")
    ap.add_argument("--min-riser", type=float, default=2.0, help="склейки раньше этого (с) без райзера")
    ap.add_argument("--events-to", choices=("pulses", "risers", "none"), default="pulses",
                    help="куда класть EVENT (по умолчанию в pulses)")
    ap.add_argument("--cues", help="music_cues.json (по умолчанию из episode.json)")
    ap.add_argument("--dry-run", action="store_true", help="не писать, только показать и сравнить")
    a = ap.parse_args()

    with open(a.episode, encoding="utf-8") as fh:
        ep = json.load(fh)
    cues_path = R(a.cues or ep.get("music_cues", f"episodes/{ep['id']}/music_cues.json"))
    cues = {}
    if os.path.isfile(cues_path):
        with open(cues_path, encoding="utf-8") as fh:
            cues = json.load(fh)
    fps = ep["format"]["fps"]
    pulses, risers, ev, src = build(ep, a.thr, parse_excludes(a.exclude), a.logs, a.min_riser, a.events_to,
                                    cues.get("duration_s"))
    for shot, log in src.items():
        print(f"LOG {shot}: {log or '-'}")
    for k, ts in ev.items():
        print(f"EVENT {k}: {ts}")
    print("PULSES", pulses)
    print("RISERS", risers)
    compare("pulses", pulses, cues.get("pulses", []), fps)
    compare("risers", risers, cues.get("risers", []), fps)
    if a.dry_run:
        print("DRY-RUN: не записано")
        return 0
    cues["pulses"], cues["risers"] = pulses, risers
    with open(cues_path, "w", encoding="utf-8") as fh:
        json.dump(cues, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("CUES", cues_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
