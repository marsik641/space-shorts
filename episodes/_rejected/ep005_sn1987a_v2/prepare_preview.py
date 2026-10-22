"""Монтажный лист черновика: после TTS/music/mix, до assemble.py.

python episodes/ep006_sn1987a/prepare_preview.py
Черновые кадры только draft/, мастер всегда из frames/.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build_edit

master_path = build_edit.main(str(HERE / "episode.json"), "en")
cfg = json.loads(Path(master_path).read_text(encoding="utf-8"))
for shot in cfg["shots"]:
    shot["dir"] = shot["dir"].replace("/frames/", "/draft/")
cfg["output"] = f"out/{HERE.name}/9x16/{HERE.name}_en_draft.mp4"
cfg["video"] = {"bitrate_kbps": 3400, "preset": "REALTIME"}
# Исходник 270×480, согласование 540×960. Все пропорции титров те же.
cfg["format"].update(w=540, h=960)
cfg["captions"]["size"] = int(round(cfg["captions"]["size"] * .5))
for title in cfg["titles"]:
    title["size"] = int(round(title["size"] * .5))
out = REPO / "out" / HERE.name / "9x16" / "edit_draft.json"
out.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
print("DRAFT_EDIT", out)
