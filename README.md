# space-shotrs — конвейер Shorts канала Orbitfall

**Orbitfall** (`@Orbitfall`) — «Real objects. Real numbers. Rendered.» Реалистичные научные визуализации
**реальных** объектов и событий всего космоса (планеты и луны, звёзды и их останки, чёрные дыры, галактики,
экзопланеты, кометы, миссии, масштаб, «что если») с параметрами из каталогов и статей → вертикальные ролики
1080×1920 60 fps с озвучкой, музыкой и субтитрами → готовый пакет к загрузке (мастер + превью для телефона +
название, описание с источниками, теги, закреп, настройки Studio). Нейтронные звёзды эп. 001 — только первая тема.

Только **EN**-версии (`languages: ["en"]`). Канал, серии, темы — `docs/channel.md`. Оформление (аватар, баннер) —
`tools/brand.py` → `out/brand/`: серп планеты в контровом свете далёкой звезды + светящаяся орбита со следом и
маленький спутник на ней, словесный знак ORBITFALL (общий космический образ, не пульсар).

Рендер — Blender 5.2 Cycles (OptiX, RTX 3060). Вся сборка — скриптами, без ручной работы в Blender.

## Структура

| Папка | Что внутри |
|---|---|
| `spacekit/` | Библиотека сцен (импортируется внутри Blender): `core`, `render`, `camera`, `anim`, `orbits`, `lighting`, `sky`, `shot`, `bodies/` (пульсар, планеты), `fx/` (пылевое кольцо, светящиеся линии орбит). Возможности и API — `docs/spacekit.md` |
| `editkit/` | Монтаж в VSE Blender (`assemble.py`: шоты + титры + субтитры + звук → MP4), проверка видео (`verify_video.py`) |
| `tools/` | Озвучка (`tts.py`), музыка (`music.py`), cue по вспышкам из логов рендера (`cues.py`), сведение (`mix.py`), монтажный лист (`build_edit.py`), проверка эпизода (`check_episode.py`), QA финального MP4 (`qa.py`, PASS/FAIL), сбор релиза (`release.py` → `out/<ep>/release/`), рендер эпизода (`render_episode.sh`; на другом ПК по ssh — `remote_render.py` + `remote/agent.py`, `docs/remote_render.md`), оформление канала (`brand.py`), контактные листы, регресс-сравнение картинок, мерцание |
| `episodes/<id>/` | Эпизод: `facts.md` (факты + источники), `system.py` (параметры объекта), `shots_*.py` (шоты), `script_*.json` (текст + тайминг), `music_cues.json`, `episode.json`, `edit_*.json` (генерирует `build_edit.py`), `publish_en.md`. Сводка шотов всех эпизодов — `episodes/INDEX.md` |
| `docs/` | `channel.md` (канал), `pipeline.md` (как делается ролик), `growth.md` (рост и деньги), `metrics.md` (метрики роликов), `spacekit.md` (что умеет библиотека), `timings.md` (замеры с/кадр и формула ETA), `approval.md` (сообщение на одобрение и что можно менять после «ок»), `publish.md` (пакет к загрузке), `remote_render.md` (рендер на другом ПК), `research/` (исследование с источниками) |
| `ideas/` | Варианты следующих роликов (`_TEMPLATE_options.md` — формат файла вариантов) |
| `out/` | Кадры, превью, аудио, готовые видео, `<ep>/release/` (пакет к загрузке), `brand/` (в git не идёт). `out/RENDER.lock` — идёт финальный рендер |
| `.claude/` | `skills/` — команды конвейера `/next-video`, `/make-video` (до пакета к загрузке включительно); `workflows.md` — промпты ролей (исследователь, фактчекер, критики превью) |

## Быстрый старт

Команды — для Git Bash (Bash tool). В PowerShell: Blender — `& 'D:\Blender\blender.exe'`, venv — `.venv\Scripts\python.exe`.

```bash
# 1. окружение для звука (один раз)
#    kokoro-onnx (НЕ пакет kokoro, которому нужен Python <3.13) работает на 3.14 через onnxruntime
py -3.14 -m venv .venv && .venv/Scripts/python -m pip install kokoro-onnx soundfile edge-tts numpy scipy pyloudnorm
# веса Kokoro (озвучка, Apache-2.0) -> assets/tts/ (папка в .gitignore, на чистом клоне её нет)
mkdir -p assets/tts
curl -L -o assets/tts/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o assets/tts/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

# 0. перед любым Blender: один Blender за раз. Есть out/RENDER.lock или blender.exe в tasklist -> только текстовая работа
ls out/RENDER.lock 2>/dev/null; tasklist | grep -i blender

# 2. проверка согласованности эпизода (stdlib, без Blender) и превью шота (50%, быстро)
python tools/check_episode.py episodes/ep001_psr_b1257/episode.json
"/d/Blender/blender.exe" -b --factory-startup -P episodes/ep001_psr_b1257/shots_9x16.py -- v4 preview 1,480,960

# 3. финальный рендер шотов (с докачкой)
bash tools/render_episode.sh episodes/ep001_psr_b1257/shots_9x16.py v1 v2 v3 v4 v5 v6

# 4. звук: озвучка -> музыка -> сведение
A=out/ep001_psr_b1257/9x16/audio
.venv/Scripts/python tools/tts.py episodes/ep001_psr_b1257/script_9x16.json en $A
.venv/Scripts/python tools/music.py episodes/ep001_psr_b1257/music_cues.json $A/music.wav
.venv/Scripts/python tools/mix.py $A/vo_en.wav $A/music.wav $A/mix_en.wav

# 5. монтажный лист и сборка мастера MP4 (40 Мбит/с)
E=episodes/ep001_psr_b1257
python tools/build_edit.py $E/episode.json en
"/d/Blender/blender.exe" -b --factory-startup -P editkit/assemble.py -- $E/edit_9x16_en.json
# -> out/ep001_psr_b1257/9x16/ep001_psr_b1257_en_1080x1920p60.mp4

# 6. QA финального MP4: размер/fps/длительность + кадры (2, каждая склейка ±1, последний) -> PNG, смотреть глазами
python tools/qa.py episodes/ep001_psr_b1257/episode.json en          # PASS/FAIL
# вручную, без qa.py:
"/d/Blender/blender.exe" -b --factory-startup -P editkit/verify_video.py -- \
  out/ep001_psr_b1257/9x16/ep001_psr_b1257_en_1080x1920p60.mp4 out/ep001_psr_b1257/9x16/qa_en \
  2,136,270,271,272,616,960,961,962,1321,1680,1681,1682,2161,2640,2641,2642,2941,3240,3241,3242,3420,3599

# 7. пакет к загрузке: publish_en.md (docs/publish.md) + сбор релиза
python tools/release.py episodes/ep001_psr_b1257/episode.json   # -> out/ep001_psr_b1257/release/: мастер MP4 + publish_en.md
```

Длительность: цель **59–59,5 с**, жёсткий максимум **60,0 с** (Shorts > 60 с с любой претензией по авторскому праву
блокируется). При 60 fps монтаж ≤ 3599 кадров: AAC округляет звуковую дорожку вверх до блоков 1024 сэмпла,
и при 3600 кадрах она выходит 60,011 с.

Как устроен полный цикл «выбрал тему → одобрил → получил готовый к загрузке ролик» — `docs/pipeline.md`.
Время шагов и ETA рендера — `docs/timings.md`.

## Озвучка: лицензии

- **Kokoro-82M** (`kokoro-onnx`, веса Apache-2.0): офлайн, без серых зон — основной движок.
- **edge-tts** (стоит в `.venv`, `tools/tts.py` его умеет): код LGPLv3, но сервис Microsoft проприетарный;
  коммерческое использование без Azure-подписки — **серая зона по ToS Microsoft**
  (`docs/research/2026-10-18_research.md`, раздел про стек). Без нужды не брать.

## Эпизоды

| # | Объект | Версии |
|---|---|---|
| 001 | PSR B1257+12 — пульсар с первыми экзопланетами | **9:16 1080p60 59,98 с EN** (3599 кадров, QA PASS) — к загрузке; RU-версия собрана в `out/`, но RU отброшен — не публикуется; 16:9 1080p30 47 с (RU титры) — архив |
| 002 | Voyager 1 — первый рукотворный объект в одном световом дне от Земли (18.11.2026) | **9:16 1080p60 59,5 с EN** (3570 кадров, QA PASS) — к загрузке **до 18.11.2026 10:16 UTC** |
| 003 | TRAPPIST-1 — семь миров размером с Землю: сосед в небе шире Луны | **9:16 1080p60 59,5 с EN** (3570 кадров, QA PASS) — к загрузке |
