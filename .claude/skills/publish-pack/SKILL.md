---
name: publish-pack
description: Подготовить пакет к загрузке готового эпизода — названия, описания EN/RU с источниками, теги, хэштеги, закреп, флажки Studio, тексты для TikTok/Reels/VK/Rutube — и собрать out/<ep>/release/. Использовать, когда пользователь говорит «пакет к загрузке», «тексты для ютуба», «/publish-pack», или в конце /make-video.
---

# /publish-pack — пакет к загрузке

Вход: эпизод `episodes/<ep>/` (facts.md, script_9x16.json, episode.json) и готовые MP4 в `out/<ep>/9x16/`.
Каркас файлов — `episodes/_template/publish_en.md`, `publish_ru.md`.

## Файлы `episodes/<ep>/publish_en.md` и `publish_ru.md`

1. **Названия** — 3 варианта, ≤ 60 символов, факт-крючок или вопрос, без кликбейт-лжи
   (пример: «This Dead Star Spins 161 Times a Second»). Отметь рекомендуемый.
2. **Описание**: 2–3 строки сути (первая строка видна в ленте) → «Visualization based on real data:» +
   ключевые параметры → **Sources** — **каждое число ролика** со ссылкой из facts.md (не влезает — в закреп) →
   «Rendered in Blender Cycles · scientific visualization / artist's impression» + условности (масштаб, замедление) →
   3–5 хэштегов (`#space #astronomy #<объект>`).
3. **Теги**: 5–8 (минимальная роль): объект, тип объекта, space, astronomy, science visualization, 3D render.
4. **Закреплённый комментарий**: источники коротко + вопрос зрителю (выбор следующей темы).
5. **Studio** (в обоих файлах; в RU — для YouTube-зеркала, язык Russian): не для детей; категория Science & Technology;
   плейлист/серия; Related video (long-form, если есть). «Altered or synthetic content» — **добровольно**: по справке
   обязательно для GenAI, Blender-рендер формально не GenAI; консервативно отмечать для фотореалистичных сцен, которых
   не было (метка не режет охват). TTS-озвучка может получить автометку YouTube.
6. **Время публикации**: стабильный слот (вечер США для EN), без «магических часов».
7. **Кросс-пост**: короткие подписи — нативные, без ссылок на YouTube; загружать чистые мастера (не скачивать с YouTube).
   - EN: TikTok — из РФ загрузка новых видео заблокирована с 03.2022 (проверить), Creator Rewards — только ролики > 60 с;
     Instagram Reels — только охват (Meta в РФ признана экстремистской, доход — юридический риск).
   - RU: VK Клипы, Rutube, Wibes. Монетизация Клипов VK и Rutube Shorts не подтверждена — проверить в справке.
     Rutube — самозанятость/ИП; при 10k+ подписчиков — реестр РКН; интеграции — с ЕРИД.

## Сборка релиза

```bash
python tools/qa.py episodes/<ep>/episode.json en      # и ru — должно быть PASS
python tools/build_edit.py episodes/<ep>/episode.json en --light   # если light-копий ещё нет; и ru
"/d/Blender/blender.exe" -b --factory-startup -P editkit/assemble.py -- episodes/<ep>/edit_9x16_en_light.json
python tools/release.py episodes/<ep>/episode.json      # → out/<ep>/release/: MP4 EN/RU, _light-копии, publish_*.md
```
Faststart/BT.709 Blender не пишет — сознательно без ремукса (`docs/pipeline.md`, «Оговорка про контейнер»).
Отправь пользователю (SendUserFile) light-копии MP4 (полные ≈ 300 МБ — путём к `out/<ep>/release/`) и `publish_*.md`.
