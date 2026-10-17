---
name: publish-pack
description: Подготовить пакет к загрузке готового эпизода — названия, описания EN/RU с источниками, теги, хэштеги, закреп, флажки Studio, тексты для TikTok/Reels/VK/Rutube — и собрать out/<ep>/release/. Использовать, когда пользователь говорит «пакет к загрузке», «тексты для ютуба», «/publish-pack», или в конце /make-video.
---

# /publish-pack — пакет к загрузке

Вход: эпизод `episodes/<ep>/` (facts.md, script_9x16.json, episode.json) и готовые MP4 в `out/<ep>/9x16/`.

## Файлы `episodes/<ep>/publish_en.md` и `publish_ru.md`

1. **Названия** — 3 варианта, ≤ 60 символов, факт-крючок или вопрос, без кликбейт-лжи
   (пример: «This Dead Star Spins 161 Times a Second»). Отметь рекомендуемый.
2. **Описание**: 2–3 строки сути (первая строка видна в ленте) → «Visualization based on real data:» +
   ключевые параметры → **Sources** (ссылки из facts.md) → «Rendered in Blender Cycles · scientific
   visualization / artist's impression» → 3–5 хэштегов (`#space #astronomy #<объект>`).
3. **Теги**: 5–8 (минимальная роль): объект, тип объекта, space, astronomy, science visualization, 3D render.
4. **Закреплённый комментарий**: источники коротко + вопрос зрителю (выбор следующей темы).
5. **Studio**: не для детей; «altered or synthetic content» — да для фотореалистичных сцен, которых не было
   (объяснить почему); категория Science & Technology; плейлист/серия; Related video (long-form, если есть).
6. **Время публикации**: стабильный слот (вечер США для EN), без «магических часов».
7. **Кросс-пост**: короткие подписи для TikTok, Instagram Reels (EN), VK Клипы, Rutube (RU) — нативные, без
   ссылок на YouTube; загружать чистые мастера (не скачивать с YouTube).

## Сборка релиза

`out/<ep>/release/`: оба MP4 + оба `publish_*.md`. Проверь `editkit/verify_video.py` (≤ 60.0 с, 1080×1920, 60 fps).
Отправь пользователю MP4 (SendUserFile; > 30 МБ — ещё лёгкая копия) и publish-файлы.
