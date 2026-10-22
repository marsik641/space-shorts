# Энцелад: карта Cassini

- Источник: https://www.jpl.nasa.gov/images/pia14937-map-of-enceladus-december-2011/
- JPEG: https://d2pn8kiwq2w21t.cloudfront.net/original_images/jpegPIA14937.jpg
- Credit: NASA/JPL-Caltech/Space Science Institute.
- Использование: https://www.jpl.nasa.gov/jpl-image-use-policy/
- `map2011.jpg`: оригинал 7480×3930, скачан 21.10.2026.
- `episodes/ep007_enceladus/enc4k.jpg`: карта без заголовка, рамки и масштаба: crop(160,140,7360,3740),
  затем LANCZOS 4096×2048. Содержимое поверхности не дорисовывалось.
- Это фотомозаика с остаточным освещением, не DEM и не точная карта альбедо.
  Поэтому в материале используется с ослабленным контрастом; из неё не строятся горы.
- Локальный рельеф южного полюса процедурный, по Porco2006; это отдельная реконструкция.
- Производная текстура лежит в папке эпизода, чтобы `remote_render.py push` включал её автоматически.

## Детали поверхности для исправленного превью

- Источник: https://www.jpl.nasa.gov/images/pia11113-damascus-sulcus-on-enceladus/
- Credit: NASA/JPL/Space Science Institute; условия использования JPL те же.
- Оригинал: `episodes/ep007_enceladus/damascus.jpg`; производная фактура: `icefine.jpg` там же.
- Шаг исходной мозаики 24 м/px. Кадрирование и нормировка описаны в `episodes/ep007_enceladus/revision_2.md`.
- Фактура применяется в цвете и слабой микронормали. Это не DEM; высоты реконструированы отдельно.
