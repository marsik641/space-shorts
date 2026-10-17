# Шаблон эпизода

Скопировать папку в `episodes/epNNN_<slug>/` и заполнить. **NNN** = max(номеров `episodes/ep*`) + 1, трёхзначный,
не переиспользуется; **slug** — `[a-z0-9_]`, ≤ 16 символов, по каталожному имени (`psr_j1748`, `trappist1`, `sgr_a`):
длинные пути ломают Blender (лимит 260 символов).

Эпизод ep001 — пример API, **не образец для копирования** (CLAUDE.md: каждый ролик уникален). JSON из ep001 не копировать:
там захардкожены пути ep001. В шаблоне явных путей нет (кроме `output` с шаблоном {id}/{lang}) — `build_edit.py` выводит `frames_dir`/`audio_dir` из `id`
(`out/<id>/9x16/frames`, `out/<id>/9x16/audio`), сценарий и cue — `episodes/<id>/script_9x16.json`, `music_cues.json`.

| Файл | Что заполнить |
|---|---|
| `facts.md` | Факты с источниками (каждое число — URL), гипотезы, условности визуализации |
| `system.py` | Реальные параметры → экранный масштаб (общие для всех шотов), docstring «реальность → экран», сиды |
| `shots_9x16.py` | Шоты 1080×1920 60 fps на `spacekit.shot` (каркас; API — `docs/spacekit.md`) |
| `script_9x16.json` | Озвучка EN/RU сегментами с якорями `at` (с), 59–59,5 с; `<lang>_cap` — цифры, `|` — ручные разрывы. Голос/темп — не как в прошлом эпизоде |
| `episode.json` | `id` = имя папки; `edit` (кадры = SHOTS), оверлеи, `caption_style` в безопасных зонах Shorts (`docs/pipeline.md`, «Титры и субтитры») |
| `music_cues.json` | Своя тональность/гармония/seed; `pulses`/`risers` заполняет `tools/cues.py` |
| `publish_en.md`, `publish_ru.md` | Пакет к загрузке (`/publish-pack`) |
| `edit_9x16_<lang>.json` | Генерирует `tools/build_edit.py` (коммитится — воспроизводимость монтажа) |

Проверка согласованности: `python tools/check_episode.py episodes/<ep>/episode.json`.
Порядок работы — `docs/pipeline.md` и команда `/make-video`.
