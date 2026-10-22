"""Один ролик (или задача) = одна git worktree: номер эпизода, ветка, ассеты, влитие в main, уборка.

    python tools/video_wt.py start [--task SLUG | --here]  из основной копии: резерв epNNN, worktree, ассеты
    python tools/video_wt.py claim SLUG                    в worktree ролика: ветка video/epNNN → video/epNNN_SLUG
    python tools/video_wt.py status                        все worktree и резервы номеров
    python tools/video_wt.py finish [--no-release]         в своей worktree: DoD → main в ветку → тесты → ff main
    python tools/video_wt.py remove NAME [--abandon]       из основной копии: убрать влитую worktree и ветку

Worktree лежат в out/wt/<NAME> основной копии (SS_WT_ROOT — переопределить): внутри папки проекта, куда пишет
песочница Codex (workspace-write); out/ в .gitignore. Claude в такой worktree читает и родительский CLAUDE.md
основной копии — при расхождении правила main новее: влить main в ветку.
Номер — create-only ref refs/video/epNNN: два чата не получат один номер; номер не переиспользуется (и у брошенных).
Игнорируемые ассеты основной копии (Млечный Путь, кеши текстур) копируются; assets/tts/ очередь берёт из основной.
finish: дерево чистое, у ролика есть release/ (мастер + publish_en.md), финал принят (accept), нет живых заданий
очереди → git merge main в ветку → check_episode + unittest → git merge --ff-only в основной копии (она на main) →
out/<ep>/ переносится в основную копию (release не теряется при удалении worktree). Эпизод — из ветки
video/epNNN_slug или, у старых веток (codex/…), по единственной папке episodes/epNNN_* в диффе с main.
remove не удаляет worktree, в которой лежит out/ep* (кадры, мастер), без явного --drop-out.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SLUG = re.compile(r"^[a-z0-9_]{1,16}$")
TASK = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
LIVE = {"queued", "running", "paused"}


def git(*args, cwd=".", check=True):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        sys.exit(f"FAIL git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r


def same(a, b):
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))


def main_root(cwd="."):
    return Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd).stdout.strip()).parent


def top(cwd="."):
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd).stdout.strip())


def wt_root(main):
    return Path(os.environ.get("SS_WT_ROOT") or main / "out" / "wt")


def worktrees(main):
    """[(путь, ветка)] всех worktree, кроме основной."""
    out, path = [], None
    for line in git("worktree", "list", "--porcelain", cwd=main).stdout.splitlines():
        if line.startswith("worktree "):
            path = Path(line[9:])
        elif line.startswith("branch ") and path and not same(path, main):
            out.append((path, line[7:].removeprefix("refs/heads/")))
    return out


def used_numbers(main):
    """Номера из main (эпизоды и брошенные), всех веток и резервов, старых worktree out/wN."""
    names = git("ls-tree", "--name-only", "main", "episodes/", cwd=main).stdout.split()
    names += git("ls-tree", "--name-only", "main", "episodes/_rejected/", cwd=main, check=False).stdout.split()
    names += git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", "refs/video", cwd=main).stdout.split()
    nums = {int(n) for s in names for n in re.findall(r"ep(\d{3})", s)}
    nums |= {int(m.group(1)) for p, _ in worktrees(main) if (m := re.fullmatch(r"w(\d{1,3})", p.name))}
    return nums


def reserve(main):
    head = git("rev-parse", "main", cwd=main).stdout.strip()
    for n in range(max(used_numbers(main) | {0}) + 1, 1000):
        r = git("update-ref", f"refs/video/ep{n:03d}", head, "0" * len(head), cwd=main, check=False)
        if r.returncode == 0:
            return n
        if "exists" not in r.stderr:                     # не гонка за номер, а настоящая ошибка
            sys.exit(f"FAIL резерв номера: {r.stderr.strip()}")
    sys.exit("FAIL свободных номеров нет")


def copy_assets(main, dest):
    """Игнорируемые файлы assets/ основной копии (кроме tts) → worktree. Копия, не hardlink: кеш, пересобранный
    в одной копии, не должен на месте перезаписать файл другой."""
    files = git("ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", "assets", cwd=main).stdout
    k = 0
    for rel in filter(None, files.split("\0")):
        src, dst = main / rel, dest / rel
        if rel.startswith("assets/tts/") or dst.exists() or not src.is_file():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        k += 1
    return k


def ep_of(branch, here=None):
    """video/ep010_kepler16b → ep010_kepler16b; до claim — None. Старая ветка (codex/…) — по единственной папке
    episodes/epNNN_* в её диффе с main."""
    if m := re.fullmatch(r"video/(ep\d{3}_[a-z0-9_]+)", branch):
        return m.group(1)
    if here is None or branch.startswith("video/"):
        return None
    names = git("diff", "--name-only", "main...HEAD", "--", "episodes/", cwd=here, check=False).stdout.split()
    eps = {m.group(1) for n in names if (m := re.match(r"episodes/(ep\d{3}_[a-z0-9_]+)/", n))}
    return eps.pop() if len(eps) == 1 else None


def cmd_start(a):
    here, main = top(), main_root()
    if a.here:
        if same(here, main):
            sys.exit("FAIL --here — только в уже созданной worktree (не в основной копии)")
        n = reserve(main)
        git("branch", "-m", f"video/ep{n:03d}", cwd=here)
        path, br = here, f"video/ep{n:03d}"
    else:
        if not same(here, main):
            sys.exit(f"FAIL start — из основной копии {main}; ты уже в worktree {here}: продолжай в ней")
        if a.task:
            if not TASK.fullmatch(a.task):
                sys.exit("FAIL --task: [a-z0-9-], ≤ 24 символов")
            name, br = f"task-{a.task}", f"task/{a.task}"
        else:
            n = reserve(main)
            name, br = f"ep{n:03d}", f"video/ep{n:03d}"
        path = wt_root(main) / name
        if path.exists():
            sys.exit(f"FAIL {path} уже есть")
        path.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "-b", br, str(path), "main", cwd=main)
    k = copy_assets(main, path)
    print(f"OK {br}\n  путь:   {path}\n  main:   {main}\n  venv:   {main / '.venv' / 'Scripts' / 'python.exe'}\n"
          f"  ассеты: скопировано {k}\nДальше вся работа и все коммиты — в этой папке "
          f"(Claude: EnterWorktree path; Codex: workdir). Основную копию не править.")
    if a.here:
        print("Worktree создана приложением: после finish её не удалять (remove не нужен) — уберёт приложение.")


def cmd_claim(a):
    here = top()
    br = git("branch", "--show-current", cwd=here).stdout.strip()
    m = re.fullmatch(r"video/ep(\d{3})", br)
    if not m:
        sys.exit(f"FAIL claim — в worktree ролика на ветке video/epNNN (сейчас {br or 'detached'})")
    if not SLUG.fullmatch(a.slug):
        sys.exit("FAIL slug: [a-z0-9_], ≤ 16 символов, по каталожному имени")
    ep = f"ep{m.group(1)}_{a.slug}"
    git("branch", "-m", f"video/{ep}", cwd=here)
    print(f"OK эпизод {ep}: ветка video/{ep}, папка episodes/{ep}/")


def dirty(path):
    # без optional locks: status по чужой worktree не пишет её index.lock и не мешает её агенту
    return git("--no-optional-locks", "status", "--porcelain", cwd=path).stdout.strip()


def cmd_status(a):
    main = main_root()
    print(f"main: {main} {git('log', '-1', '--format=%h %s', 'main', cwd=main).stdout.strip()}")
    for path, br in worktrees(main):
        ahead = git("rev-list", "--count", f"main..{br}", cwd=main, check=False).stdout.strip() or "?"
        last = git("log", "-1", "--format=%cr: %s", br, cwd=main, check=False).stdout.strip()
        ep = ep_of(br, path if path.exists() else None)
        rel = "release ✓" if ep and (path / "out" / ep / "release").is_dir() else ""
        state = "грязно" if path.exists() and dirty(path) else "чисто"
        print(f"  {br:32} {state:6} +{ahead:<3} {rel:9} {path}\n      {last}")
    refs = git("for-each-ref", "--format=%(refname:short)", "refs/video", cwd=main).stdout.split()
    print("резервы номеров: " + (", ".join(r.split("/")[-1] for r in refs) or "нет"))
    print(f"следующий номер: ep{max(used_numbers(main) | {0}) + 1:03d}")


def queue_jobs(here):
    """Задания общей очереди, поставленные из этой worktree; None — очередь недоступна."""
    r = subprocess.run([sys.executable, str(here / "tools" / "render_queue.py"), "status", "--json"],
                       capture_output=True, encoding="utf-8", errors="replace")
    try:
        jobs = json.loads(r.stdout).get("jobs", [])
    except ValueError:
        return None
    return [j for j in jobs if same(j.get("source", ""), here)]


def check_release(here, ep, jobs):
    rel = here / "out" / ep / "release"
    if not (list(rel.glob("*.mp4")) and (rel / "publish_en.md").is_file()):
        sys.exit(f"FAIL нет пакета {rel}: мастер MP4 + publish_en.md")
    if jobs is None:                                     # очереди нет — по последнему результату
        res = here / "out" / ep / "queue_result.json"
        if res.is_file() and json.loads(res.read_text(encoding="utf-8")).get("review_required"):
            sys.exit("FAIL визуальный QA не принят: render_queue.py accept JOB")
        return
    # queue_result.json перезаписывает любое следующее превью — судим по самим заданиям финала
    finals = [j for j in jobs if j.get("kind") == "final" and j.get("episode") == ep]
    if waiting := [j["id"] for j in finals if j.get("state") == "needs_review"]:
        sys.exit("FAIL визуальный QA не принят: render_queue.py accept " + ", ".join(waiting))
    if not any(j.get("state") == "done" for j in finals):
        sys.exit(f"FAIL в очереди нет принятого финала {ep} из этой worktree")


def cmd_finish(a):
    here, main = top(), main_root()
    if same(here, main):
        sys.exit("FAIL finish — из своей worktree, не из основной копии")
    if git("branch", "--show-current", cwd=main).stdout.strip() != "main":
        sys.exit("FAIL основная копия не на ветке main — не вливаю (спросить владельца)")
    br = git("branch", "--show-current", cwd=here).stdout.strip()
    if d := dirty(here):
        sys.exit("FAIL грязное дерево — закоммить логическими блоками (AGENTS.md, «Работа агентов»):\n" + d)
    ep = ep_of(br, here)
    if br.startswith("video/") and not ep and not a.no_release:
        sys.exit("FAIL у ветки ролика нет эпизода: сначала claim SLUG (или --no-release для брошенного)")
    jobs = queue_jobs(here)
    if ep and not a.no_release:
        check_release(here, ep, jobs)
    if live := [j for j in jobs or [] if j.get("state") in LIVE]:
        sys.exit("FAIL живые задания очереди из этой worktree: " + ", ".join(f"{j['id']} {j['state']}" for j in live))
    r = git("merge", "--no-edit", "-m", f"chore(merge): main → {br}", "main", cwd=here, check=False)
    if r.returncode:
        sys.exit("FAIL конфликт при git merge main — реши в этой worktree (чужие правки сохранить), закоммить, "
                 "повтори finish:\n" + git("diff", "--name-only", "--diff-filter=U", cwd=here).stdout)
    checks = [[sys.executable, "-m", "unittest", "discover", "-s", "tests"]]
    if ep and (here / "episodes" / ep / "episode.json").is_file():
        checks.insert(0, [sys.executable, "tools/check_episode.py", f"episodes/{ep}/episode.json"])
    for cmd in checks:
        if subprocess.run(cmd, cwd=here).returncode:
            sys.exit(f"FAIL {' '.join(cmd[1:])} — чинить в worktree, коммит, повтор finish")
    r = git("merge", "--ff-only", br, cwd=main, check=False)
    if r.returncode:
        sys.exit("FAIL ff main не прошёл (main сдвинулся или в основной копии мешают файлы) — повтори finish:\n"
                 + (r.stderr or r.stdout).strip())
    moved = ""
    if ep and (here / "out" / ep).is_dir():
        dst = main / "out" / ep
        if dst.exists():
            moved = f"\n  WARN {dst} уже есть — out/{ep} остался в worktree, перенеси вручную"
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(here / "out" / ep), str(dst))
            moved = f"\n  out/{ep} → {dst}"
    print(f"OK {br} влита в main ({git('log', '-1', '--format=%h', 'main', cwd=main).stdout.strip()}){moved}\n"
          f"Дальше: выйти из worktree (Claude: ExitWorktree keep) и из основной копии — "
          f"python tools/video_wt.py remove {here.name}")


def cmd_remove(a):
    main = main_root()
    hit = [(p, b) for p, b in worktrees(main) if p.name == a.name]
    if not hit:
        sys.exit(f"FAIL нет worktree {a.name}")
    path, br = hit[0]
    if same(top(), path):
        sys.exit("FAIL remove — не изнутри удаляемой worktree")
    if path.exists() and (d := dirty(path)):
        sys.exit("FAIL в worktree незакоммиченные правки — не удаляю:\n" + d)
    merged = git("merge-base", "--is-ancestor", br, "main", cwd=main, check=False).returncode == 0
    if not merged and not a.abandon:
        sys.exit(f"FAIL {br} не влита в main: finish, или --abandon (ветка останется, worktree уйдёт)")
    kept = [p.name for p in (path / "out").glob("ep*") if p.is_dir() and any(p.iterdir())]
    if kept and not a.drop_out:
        sys.exit(f"FAIL в {path / 'out'} лежат {', '.join(kept)} (кадры, мастер): перенеси в out/ основной копии "
                 "или --drop-out, если они не нужны")
    git("worktree", "remove", "--force", str(path), cwd=main)  # --force — ради игнорируемых ассетов и out/
    if merged:
        git("branch", "-d", br, cwd=main)
    print(f"OK worktree {path} удалена; ветка {br} {'удалена' if merged else 'оставлена (не влита)'}")


def main():
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="worktree на ролик/задачу: start → claim → finish → remove")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--task", help="не ролик: worktree task-SLUG на ветке task/SLUG")
    g.add_argument("--here", action="store_true", help="уже в worktree (создана приложением): резерв номера")
    sub.add_parser("claim").add_argument("slug")
    sub.add_parser("status")
    sub.add_parser("finish").add_argument("--no-release", action="store_true", help="задача или брошенный ролик")
    p = sub.add_parser("remove")
    p.add_argument("name")
    p.add_argument("--abandon", action="store_true")
    p.add_argument("--drop-out", action="store_true", help="удалить и out/ep* worktree (кадры, мастер)")
    a = ap.parse_args()
    dict(start=cmd_start, claim=cmd_claim, status=cmd_status, finish=cmd_finish, remove=cmd_remove)[a.cmd](a)


if __name__ == "__main__":
    main()
