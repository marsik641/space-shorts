# space-shotrs — конвейер космических Shorts

Реалистичные научные визуализации **реальных** космических объектов (пульсары, магнитары, чёрные дыры,
экзопланеты с параметрами из каталогов) → вертикальные ролики 1080×1920 60 fps с озвучкой, музыкой
и субтитрами → готовый пакет к загрузке (видео + название + описание + теги + закреп).

Рендер — Blender 5.2 Cycles (OptiX, RTX 3060). Вся сборка — скриптами, без ручной работы в Blender.

## Структура

| Папка | Что внутри |
|---|---|
| `spacekit/` | Библиотека сцен (импортируется внутри Blender): `core`, `render`, `camera`, `anim`, `orbits`, `lighting`, `sky`, `shot`, `bodies/` (пульсар, планеты), `fx/` (пылевое кольцо) |
| `editkit/` | Монтаж в VSE Blender (`assemble.py`: шоты + титры + субтитры + звук → MP4), проверка видео (`verify_video.py`) |
| `tools/` | Озвучка (`tts.py`), музыка (`music.py`), сведение (`mix.py`), рендер эпизода (`render_episode.sh`), контактные листы, регресс-сравнение картинок, мерцание |
| `episodes/<id>/` | Эпизод: `system.py` (параметры объекта), `shots_*.py` (шоты), `script_*.json` (текст + тайминг), `music_cues.json`, `edit_*.json`, `publish_*.md` |
| `docs/` | `channel.md` (канал), `pipeline.md` (как делается ролик), `growth.md` (рост и деньги), `research/` (исследование с источниками) |
| `out/` | Кадры, превью, аудио, готовые видео (в git не идёт) |
| `.claude/skills/` | Команды конвейера для Claude Code: `/next-video`, `/make-video`, `/publish-pack` |

## Быстрый старт

```bash
# 1. окружение для звука (один раз)
py -3.14 -m venv .venv && .venv/Scripts/python -m pip install kokoro-onnx soundfile edge-tts numpy scipy pyloudnorm
# веса Kokoro (EN-озвучка, Apache-2.0) -> assets/tts/
curl -L -o assets/tts/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o assets/tts/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

# 2. превью шота (50%, быстро)
"/d/Blender/blender.exe" -b --factory-startup -P episodes/ep001_psr_b1257/shots_9x16.py -- v4 preview 1,480,960

# 3. финальный рендер шотов (с докачкой)
bash tools/render_episode.sh episodes/ep001_psr_b1257/shots_9x16.py v1 v2 v3 v4 v5 v6

# 4. звук: озвучка -> музыка -> сведение
.venv/Scripts/python tools/tts.py episodes/ep001_psr_b1257/script_9x16.json en out/ep001_psr_b1257/9x16/audio
.venv/Scripts/python tools/music.py episodes/ep001_psr_b1257/music_cues.json out/ep001_psr_b1257/9x16/audio/music.wav
.venv/Scripts/python tools/mix.py out/.../vo_en.wav out/.../music.wav out/.../mix_en.wav

# 5. монтажный лист и сборка MP4
python tools/build_edit.py episodes/ep001_psr_b1257/episode.json en
"/d/Blender/blender.exe" -b --factory-startup -P editkit/assemble.py -- episodes/ep001_psr_b1257/edit_9x16_en.json
```

Как устроен полный цикл «выбрал тему → одобрил → получил готовый к загрузке ролик» — `docs/pipeline.md`.

## Эпизоды

| # | Объект | Версии |
|---|---|---|
| 001 | PSR B1257+12 — пульсар с первыми экзопланетами | 16:9 1080p30 47 с (RU титры); 9:16 1080p60 60 с EN/RU с озвучкой |
