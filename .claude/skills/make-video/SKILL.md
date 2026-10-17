---
name: make-video
description: Произвести вертикальный космический Shorts по выбранному варианту — факты, сценарий EN/RU, сцена в spacekit, шоты, превью на одобрение, затем рендер 1080x1920p60, озвучка, музыка, монтаж и QA. Использовать, когда пользователь говорит «делаем вариант N», «/make-video», «запускай ролик про X».
---

# /make-video — производство эпизода

Вход: выбранный вариант из **самого свежего** `ideas/*_options.md` (или объект, названный пользователем) + правки.
Выход: `out/<ep>/9x16/<ep>_{en,ru}_1080x1920p60.mp4` + `out/<ep>/release/`.
Процесс и правила — `docs/pipeline.md`; одобрение — `docs/approval.md`; роли воркфлоу — `.claude/workflows.md`;
API библиотеки — `docs/spacekit.md`; время — `docs/timings.md`; грабли окружения — `CLAUDE.md`.
Команды — Git Bash (Bash tool) из корня репо; `<ep>` = `epNNN_<slug>`.

## Шаг 0 — GPU свободен?

```bash
ls out/RENDER.lock 2>/dev/null; tasklist //FI "IMAGENAME eq blender.exe" | grep -i blender
```
Если есть lock или `blender.exe` — **только текстовая работа** (шаги 1–5 без превью: факты, сценарий, `system.py`,
код шотов, publish-тексты). Превью, TTS, музыку — в очередь; пользователю — ETA текущего рендера (число PNG в
`out/<эпизод>/9x16/frames/<шот>/` против кадров шота, с/кадр — `docs/timings.md`). Повторять проверку перед каждым
запуском Blender/TTS. Один Blender за раз.

## Часть A — до одобрения (1–2 ч без новых модулей, +3–8 ч на модуль)

1. **Эпизод.** NNN = max(номеров `episodes/ep*`) + 1, трёхзначный, не переиспользуется; slug — `[a-z0-9_]`,
   ≤ 16 символов, по каталожному имени (`psr_j1748`, `trappist1`, `sgr_a`). Скопировать `episodes/_template/` →
   `episodes/<ep>/`, в `episode.json` — `id` = имя папки (пути `frames_dir`/`audio_dir` не задавать: build_edit
   выводит их из id). В конец ideas-файла дописать: `Выбран: N, <дата>, правки: …, эпизод: <ep>`.
2. **Факты**: исследователь + фактчекер (`.claude/workflows.md`) → `facts.md` (каждое число со ссылкой).
3. **Сценарий** `script_9x16.json`: 8–10 сегментов EN/RU, якоря `at` (с), длительность 59–59,5 с (≤ 60.0 жёстко);
   первая фраза — факт-крючок; финальная подводит к началу (петля). EN ≈ 120–150 слов. `<lang>_cap` — цифры,
   `|` — ручные разрывы (`docs/pipeline.md`, «Титры и субтитры»). Голос/темп — не как в прошлом эпизоде.
4. **Сцена**: `system.py` (реальные параметры → экран через `spacekit.orbits.video_periods`, масштаб в docstring);
   недостающее — новыми модулями `spacekit/` (+ регресс: `tools/imgdiff.py` на кадрах эп. 001).
5. **Шоты** `shots_9x16.py` (5–7 шотов на `spacekit.shot`), `episode.json` (edit, оверлеи, субтитры в безопасных зонах),
   `music_cues.json` (своя тональность/лад/темп). Склейки — встык, по возможности на событиях; последний кадр = первый.
   Проверка: `python tools/check_episode.py episodes/<ep>/episode.json` — до превью и до финала.
6. **Превью** (шаг 0!) — по одному шоту, кадры 1, n/3, 2n/3, n:
   ```bash
   mkdir -p out/<ep>/9x16/logs
   "/d/Blender/blender.exe" -b --factory-startup -P episodes/<ep>/shots_9x16.py -- vN preview 1,<n/3>,<2n/3>,<n> > out/<ep>/9x16/logs/prev_vN.log 2>&1
   "/d/Blender/blender.exe" -b --factory-startup -P tools/contact.py -- out/<ep>/9x16/sheet_prev<k>.png 4 360 out/<ep>/9x16/previews/v*_f*.png
   .venv/Scripts/python tools/tts.py episodes/<ep>/script_9x16.json en out/<ep>/9x16/audio   # и ru; нет OVERRUN
   python tools/cues.py episodes/<ep>/episode.json --logs out/<ep>/9x16/logs                  # FLASH/EVENT из превью → pulses/risers
   ```
   Превью — в `out/<ep>/9x16/previews/<шот>_fNNNN.png`; в логе — `Traceback` нет, строки `FLASH`/`EVENT` есть где ожидались.
   `<k>` — номер круга превью.
7. **Критика превью**: критики из `.claude/workflows.md` → правки → повтор превью. **Не больше 2 раундов.**
8. **Одобрение**: сообщение по шаблону `docs/approval.md` + SendUserFile (контактные листы). **Остановись и жди ответа.**

## Часть B — после «ок» (без вопросов, кроме остановок из `docs/approval.md`)

9. **Рендер** в фоне (шаг 0!): `bash tools/render_episode.sh episodes/<ep>/shots_9x16.py v1 … vN` — пишет
   `out/RENDER.lock`, логи `out/logs/<ep>/render_<шот>.log`. CPU параллельно не грузить; следить Monitor'ом раз в 30 мин;
   на ошибке — чинить и перезапускать (докачка). ETA > 1.5× заявленного — остановка и вопрос.
10. Пока рендер (только текст): `publish_en.md`/`publish_ru.md` (`/publish-pack`, без видео), `episodes/INDEX.md` (черновик строки).
11. **После рендера** (lock снят):
    ```bash
    python tools/cues.py episodes/<ep>/episode.json                       # уточнить по финальным логам
    .venv/Scripts/python tools/tts.py episodes/<ep>/script_9x16.json en out/<ep>/9x16/audio
    .venv/Scripts/python tools/tts.py episodes/<ep>/script_9x16.json ru out/<ep>/9x16/audio
    .venv/Scripts/python tools/music.py episodes/<ep>/music_cues.json out/<ep>/9x16/audio/music.wav
    .venv/Scripts/python tools/mix.py out/<ep>/9x16/audio/vo_en.wav out/<ep>/9x16/audio/music.wav out/<ep>/9x16/audio/mix_en.wav
    .venv/Scripts/python tools/mix.py out/<ep>/9x16/audio/vo_ru.wav out/<ep>/9x16/audio/music.wav out/<ep>/9x16/audio/mix_ru.wav
    python tools/build_edit.py episodes/<ep>/episode.json en               # → episodes/<ep>/edit_9x16_en.json
    "/d/Blender/blender.exe" -b --factory-startup -P editkit/assemble.py -- episodes/<ep>/edit_9x16_en.json
    python tools/build_edit.py episodes/<ep>/episode.json en --light       # 6 Мбит/с для телефона
    "/d/Blender/blender.exe" -b --factory-startup -P editkit/assemble.py -- episodes/<ep>/edit_9x16_en_light.json
    ```
    То же для `ru`.
12. **QA**: `python tools/qa.py episodes/<ep>/episode.json en` и `ru` → должно быть PASS. Затем глазами по PNG:
    субтитры в безопасных зонах, рассинхрон Kokoro в середине длинных фраз, петля, нет битых кадров. FAIL — чинить.
13. **Релиз**: `/publish-pack` → `python tools/release.py episodes/<ep>/episode.json` → `out/<ep>/release/`;
    SendUserFile: light-копии MP4 и `publish_*.md` (полные MP4 — путь).
14. **Учёт**:
    - `episodes/INDEX.md` — строка эпизода + шоты (план, ракурс, приём), голос, тональность, тип хука;
    - `README.md` → таблица «Эпизоды»;
    - `docs/channel.md` → «Первые темы»: тема отмечена `✅ эп. NNN` (если темы нет в таблице — добавить строкой);
    - коммит (код эпизода, новые модули, `edit_9x16_{en,ru}.json` — для воспроизводимости монтажа; без `out/`).
