---
name: make-video
description: Произвести вертикальный космический Shorts для The Universe Inside Out (только EN) по выбранному варианту — факты, сценарий, сцена в spacekit, шоты, превью на одобрение, затем рендер 1080x1920p60 на свободном из двух ПК (этот / rinat-pc), озвучка, музыка, монтаж, QA и готовый пакет к загрузке (out/<ep>/release/: мастер MP4 и publish_en.md). Использовать, когда пользователь говорит «делаем вариант N», «/make-video», «запускай ролик про X», «пакет к загрузке».
---

# /make-video — производство эпизода до пакета к загрузке

Вход: выбранный вариант из **самого свежего** `ideas/*_options.md` (или объект, названный пользователем) + правки.
Выход (итог после «ок» пользователя) — **пакет к загрузке** `out/<ep>/release/`: мастер
`<ep>_en_1080x1920p60.mp4` и `publish_en.md` — два файла, без `_light`/`_preview`-копий.
**Только EN**: `languages: ["en"]`, RU-шагов нет (CLAUDE.md).
Процесс и правила — `docs/pipeline.md`; одобрение — `docs/approval.md`; пакет к загрузке — `docs/publish.md`;
роли воркфлоу — `.claude/workflows.md`; API библиотеки — `docs/spacekit.md`; время — `docs/timings.md`;
грабли окружения — `CLAUDE.md`. Команды — Git Bash (Bash tool) из корня репо; `<ep>` = `epNNN_<slug>`.

## Шаг 0 — GPU свободен?

```bash
ls out/RENDER.lock 2>/dev/null; tasklist //FI "IMAGENAME eq blender.exe" | grep -i blender
```
Если есть lock или `blender.exe` — **только текстовая работа** (шаги 1–5 без превью: факты, сценарий, `system.py`,
код шотов, `publish_en.md`). Превью, TTS, музыку — в очередь; пользователю — ETA текущего рендера (число PNG в
`out/<эпизод>/9x16/frames/<шот>/` против кадров шота, с/кадр — `docs/timings.md`). Повторять проверку перед каждым
запуском Blender/TTS. Один Blender за раз.

## Часть A — до одобрения (1–2 ч без новых модулей, +3–8 ч на модуль)

1. **Эпизод.** NNN = max(номеров `episodes/ep*`) + 1, трёхзначный, не переиспользуется; slug — `[a-z0-9_]`,
   ≤ 16 символов, по каталожному имени (`psr_j1748`, `trappist1`, `sgr_a`). Скопировать `episodes/_template/` →
   `episodes/<ep>/`, в `episode.json` — `id` = имя папки, `languages: ["en"]` (пути `frames_dir`/`audio_dir` не
   задавать: build_edit выводит их из id). В конец ideas-файла дописать: `Выбран: N, <дата>, правки: …, эпизод: <ep>`.
2. **Факты**: исследователь + фактчекер (`.claude/workflows.md`) → `facts.md` (каждое число со ссылкой).
3. **Сценарий** `script_9x16.json` (EN): 8–10 сегментов, якоря `at` (с), длительность 59–59,5 с (≤ 60.0 жёстко);
   первая фраза — факт-крючок; финальная подводит к началу (петля). ≈ 120–150 слов. `en_cap` — цифры,
   `|` — ручные разрывы (`docs/pipeline.md`, «Титры и субтитры»). Голос канала — Kokoro `af_heart` ×0.98 (решение владельца).
4. **Сцена**: `system.py` (реальные параметры → экран через `spacekit.orbits.video_periods`, масштаб в docstring);
   недостающее — новыми модулями `spacekit/` (+ регресс: `tools/imgdiff.py` на кадрах эп. 001).
5. **Шоты** `shots_9x16.py` (5–7 шотов на `spacekit.shot`), `episode.json` (edit, оверлеи `en`, субтитры в безопасных
   зонах), `music_cues.json` (своя тональность/лад/темп). Склейки — встык, по возможности на событиях; последний
   кадр = первый. Σ кадров монтажа ≤ **3599** при 60 fps (AAC округляет звук вверх: 3600 кадров → 60,011 с → FAIL).
   Проверка: `python tools/check_episode.py episodes/<ep>/episode.json` — до превью и до финала.
6. **Превью** (шаг 0!) — по одному шоту, кадры 1, n/3, 2n/3, n:
   ```bash
   mkdir -p out/<ep>/9x16/logs
   "/d/Blender/blender.exe" -b --factory-startup -P episodes/<ep>/shots_9x16.py -- vN preview 1,<n/3>,<2n/3>,<n> > out/<ep>/9x16/logs/prev_vN.log 2>&1
   "/d/Blender/blender.exe" -b --factory-startup -P tools/contact.py -- out/<ep>/9x16/sheet_prev<k>.png 4 360 out/<ep>/9x16/previews/v*_f*.png
   .venv/Scripts/python tools/tts.py episodes/<ep>/script_9x16.json en out/<ep>/9x16/audio   # нет OVERRUN
   python tools/cues.py episodes/<ep>/episode.json --logs out/<ep>/9x16/logs                  # FLASH/EVENT из превью → pulses/risers
   ```
   Превью — в `out/<ep>/9x16/previews/<шот>_fNNNN.png`; в логе — `Traceback` нет, строки `FLASH`/`EVENT` есть где ожидались.
   `<k>` — номер круга превью.
7. **Критика превью**: критики из `.claude/workflows.md` → правки → повтор превью. **Не больше 2 раундов.**
8. **Одобрение**: сообщение по шаблону `docs/approval.md` + SendUserFile (контактные листы). **Остановись и жди ответа.**

## Часть B — после «ок»: до пакета к загрузке (без вопросов, кроме остановок из `docs/approval.md`)

9. **Рендер** в фоне. ПК два — этот и rinat-pc; какой свободен, выбрать самому по `docs/remote_render.md`
   («Два ПК: какой свободен»; оба свободны → rinat-pc), пользователю — какой выбран и ETA.
   - rinat-pc: `python tools/remote_render.py push` → `start` → `pull --watch` в фоне (кадры и логи — сюда).
   - этот ПК (шаг 0!): `bash tools/render_episode.sh episodes/<ep>/shots_9x16.py v1 … vN` — пишет
     `out/RENDER.lock`, логи `out/logs/<ep>/render_<шот>.log`; CPU параллельно не грузить.
   Следить раз в 30 мин; на ошибке — чинить и перезапускать (докачка). ETA > 1.5× заявленного — остановка и вопрос.
   Пока на ПК идёт рендер другого ролика — туда не `push`, а локально не менять `spacekit/` (шоты импортируют его
   заново на каждом шоте).
10. **Пока рендер (только текст):** черновик `episodes/<ep>/publish_en.md` по `docs/publish.md` (каркас —
    `episodes/_template/publish_en.md`), черновик строки `episodes/INDEX.md`.
11. **После рендера** (все кадры здесь; локальный lock снят) — звук и сборка мастера EN:
    ```bash
    A=out/<ep>/9x16/audio
    python tools/cues.py episodes/<ep>/episode.json                       # уточнить по финальным логам
    .venv/Scripts/python tools/tts.py episodes/<ep>/script_9x16.json en $A
    .venv/Scripts/python tools/music.py episodes/<ep>/music_cues.json $A/music.wav
    .venv/Scripts/python tools/mix.py $A/vo_en.wav $A/music.wav $A/mix_en.wav
    python tools/build_edit.py episodes/<ep>/episode.json en               # мастер 40 Мбит/с → edit_9x16_en.json
    "/d/Blender/blender.exe" -b --factory-startup -P editkit/assemble.py -- episodes/<ep>/edit_9x16_en.json
    ```
    Копии `--light`/`--preview` не собирать: пакет — мастер + `publish_en.md`.
12. **QA**: `python tools/qa.py episodes/<ep>/episode.json en` → PASS. Затем глазами по PNG:
    субтитры в безопасных зонах, рассинхрон Kokoro в середине длинных фраз, петля, нет битых кадров. FAIL — чинить.
13. **Пакет к загрузке** (`docs/publish.md`):
    - дописать `publish_en.md` по финальному ролику: длительность, названия, описание со **всеми** источниками,
      теги, хэштеги, закреп, Studio (вкл. добровольную метку synthetic), Related video, слот публикации,
      подписи TikTok/Reels EN;
    - `python tools/release.py episodes/<ep>/episode.json` → `out/<ep>/release/`: мастер и `publish_en.md`, больше
      ничего (нет одного из них → FAIL; файлы не из текущего состава release.py удаляет сам);
    - **SendUserFile**: оба файла из `release/` (мастер ≈ 230–300 МБ; не проходит по размеру — путь к
      `out/<ep>/release/`). Это и есть итог `/make-video`.
14. **Учёт**:
    - `episodes/INDEX.md` — строка эпизода + шоты (план, ракурс, приём), голос, тональность, тип хука;
    - `README.md` → таблица «Эпизоды»;
    - `docs/channel.md` → «Первые темы»: тема отмечена `✅ эп. NNN` (если темы нет в таблице — добавить строкой);
    - коммит (код эпизода, новые модули, `edit_9x16_en.json` — для воспроизводимости монтажа, `publish_en.md`; без `out/`).
