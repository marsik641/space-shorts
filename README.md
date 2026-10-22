# space-shotrs — конвейер Shorts канала The Universe Inside Out

**The Universe Inside Out** (`@TheUniverseInsideOut`) — «Real objects. Real numbers. Turned inside out.» Кинематографичные
визуализации **реальных** объектов и событий всего космоса (планеты и луны, звёзды и их останки, чёрные дыры,
галактики, экзопланеты, кометы, миссии, масштаб, «что если»): числа — из каталогов и статей, картинка — уровня
кино (`docs/quality.md`) → вертикальные ролики 1080×1920 60 fps до 30 с с озвучкой, музыкой и субтитрами → пакет к
загрузке (мастер MP4 + `publish_en.md`: название, описание с источниками, теги, закреп, настройки Studio).

Только **EN**-версии (`languages: ["en"]`). Канал, серии, темы — `docs/channel.md`. Оформление (аватар, баннер) —
`tools/brand.py` → `out/brand/`: каменная планета в разрезе — в вырезанном секторе светятся кора, мантия и ядро
(«наизнанку»), на баннере — THE UNIVERSE / INSIDE OUT (общий космический образ, не пульсар).

Рендер — Blender 5.2 Cycles (OptiX, RTX 3060). Вся сборка — скриптами, без ручной работы в Blender.

**Как идёт работа** (`AGENTS.md`, `docs/pipeline.md`): один ролик = один чат = одна git worktree.
`/next-video` → `tools/video_wt.py start` (номер эпизода, worktree `out/wt/epNNN`) → 3 варианта →
`/make-video N` → факты, бриф, шоты, hero-кадры → одобрение → финал через общую очередь двух ПК
(`tools/render_queue.py`, [docs/render_queue.md](docs/render_queue.md)) → release → `video_wt.py finish` (ветка
влита в main). Несколько агентов (Claude, Codex) работают параллельно, каждый в своей worktree. Планка картинки —
[docs/quality.md](docs/quality.md). Прямые команды быстрого старта ниже — справочник отдельных операций; в работе
чаты используют очередь.

## Структура

| Папка | Что внутри |
|---|---|
| `spacekit/` | Библиотека сцен (импортируется внутри Blender): `core`, `render`, `camera`, `anim`, `orbits`, `lighting`, `sky`, `shot`, `bodies/` (пульсар, планеты), `fx/` (пылевое кольцо, светящиеся линии орбит). Возможности и API — `docs/spacekit.md` |
| `editkit/` | Монтаж в VSE Blender (`assemble.py`: шоты + титры + субтитры + звук → MP4), проверка видео (`verify_video.py`) |
| `tools/` | Озвучка (`tts.py`), музыка (`music.py`), cue по вспышкам из логов рендера (`cues.py`), сведение (`mix.py`), монтажный лист (`build_edit.py`), проверка эпизода (`check_episode.py`), проверка кадров до сборки (`framecheck.py`, PASS/FAIL), QA финального MP4 (`qa.py`, PASS/FAIL), сбор релиза (`release.py` → `out/<ep>/release/`), общая очередь рендера двух ПК (`render_queue.py`, `docs/render_queue.md`; транспорт на rinat-pc — `remote_render.py` + `remote/agent.py`), worktree ролика/задачи (`video_wt.py`), оформление канала (`brand.py`), контактные листы, регресс-сравнение картинок, мерцание |
| `episodes/<id>/` | Эпизод: `facts.md` (факты + источники), `visual_brief.md` (постановка), `system.py` (параметры объекта), `shots_*.py` (шоты), `script_*.json` (текст + тайминг), `music_cues.json`, `episode.json`, `edit_*.json` (генерирует `build_edit.py`), `publish_en.md`. Сводка шотов всех эпизодов — `episodes/INDEX.md` |
| `docs/` | `channel.md` (канал), `pipeline.md` (как делается ролик), `growth.md` (рост и деньги), `metrics.md` (метрики роликов), `spacekit.md` (что умеет библиотека), `timings.md` (замеры с/кадр и формула ETA), `quality.md` (планка картинки и бюджет рендера), `workflows.md` (роли: исследователь, фактчекер, постановщик, критики), `approval.md` (сообщение на одобрение и что можно менять после «ок»), `publish.md` (пакет к загрузке), `remote_render.md` (рендер на другом ПК), `research/` (исследование с источниками) |
| `ideas/` | Варианты следующих роликов (`_TEMPLATE_options.md` — формат файла вариантов) |
| `out/` | Кадры, превью, аудио, готовые видео, `<ep>/release/` (пакет к загрузке), `brand/`, `q/` — общая очередь рендера (в git не идёт) |
| `.claude/`, `.agents/` | `skills/` — команды конвейера `/next-video`, `/make-video` для Claude и Codex (одинаковые копии, `tests/test_harness.py`) |
| `tests/` | Тесты без GPU и сети: очередь, worktree, длительность, харнесс (`python -m unittest discover -s tests`) |

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
bash tools/render_episode.sh episodes/ep001_psr_b1257/shots_9x16.py v1 v2 v3 v4 v5 v6 --approved 'одобрение из чата'

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

Длительность новых выпусков с ep009: цель **29–29,5 с**, жёсткий максимум **30,0 с**.
При 60 fps монтаж ≤ **1799 кадров**, целевой — 1770: AAC округляет звук вверх,
1800 кадров дают дорожку около 30,016 с. Решение владельца 22.10.2026; прежние готовые
эпизоды сохраняют исторические длительности. Подробно — `docs/shorts_format.md`.

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
| 004 | Кольца Сатурна — 270 000 км в поперечнике и около 10 м толщиной; кольцо изнутри | **9:16 1080p60 59,5 с EN** (3570 кадров, QA PASS) — к загрузке |
| 005 | SN 1987A | **БРАК — НЕ ВЫПУСКАЕМ.** Обе версии отклонены владельцем 20.10.2026; тема отложена |
| 006 | DART → Диморф — управляемый удар изменил орбиту астероида | **9:16 1080p60 42 с EN**, 2520 кадров, QA PASS — пакет готов; мастер отправлен в «Избранное» |
| 007 | Энцелад — океан подо льдом, струи и химические следы | **9:16 1080p60 59,5 с EN**, 3570 кадров, framecheck / QA PASS — пакет готов; мастер отправлен в «Избранное» |

**ep008** занят KELT-9b в отдельном чате; следующий свободный номер — **ep009**.
Переделка SN 1987A с прежним рабочим именем `ep006_sn1987a` — вторая забракованная версия ep005;
исходники сохранены в `episodes/_rejected/ep005_sn1987a_v2/`.
