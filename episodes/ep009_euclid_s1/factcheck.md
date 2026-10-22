# Ep009 — фактчек цепочки обнаружения C/2026 S1 (Euclid)

Проверка: 2026-10-22. Роль «Фактчекер» из `.claude/workflows.md`.
Проверены `facts.md`, `script_9x16.json`, `system.py`, текст и комментарии `shots_9x16.py`, а также полноценный `publish_en.md` со статусом DRAFT. Прочитаны также `research_notes.md` для границ утверждений и `episode.json` для плановых параметров. Blender, TTS и музыка не запускались; другие файлы этим проверяющим не менялись.

**Вердикт по доступным материалам: PASS фактов.** Научная цепочка подтверждается; фактическое содержание `publish_en.md` DRAFT принято. Две замеченные формулировки исправлены основным исполнителем и повторно прочитаны: о каталогах и о 72-часовом окне. Технический выпускной статус останется DRAFT до последующих производственных проверок.

## Первичные источники, открытые в этой проверке

- [E1 — ESA, открытие, 19.10.2026](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet).
- [E2 — ESA, контекстный длинный кадр](https://www.esa.int/ESA_Multimedia/Images/2026/10/Comet_C_2026_S1_Euclid_observations_in_context).
- [E3 — ESA, серия трёх длинных кадров](https://www.esa.int/ESA_Multimedia/Images/2026/10/Comet_C_2026_S1_Euclid_streaks_across_the_sky).
- [E4 — ESA, композит коротких экспозиций](https://www.esa.int/ESA_Multimedia/Images/2026/10/A_composite_of_eight_Euclid_VIS_exposures_of_Comet_C_2026_S1_Euclid).
- [E5 — ESA, цели Euclid](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Top_five_mysteries_Euclid_will_help_solve).
- [C1 — Euclid Consortium, описание обнаружения](https://www.euclid-ec.org/euclids-first-comet-discovery/).
- [P1 — Pöntinen et al. 2020, §4.1](https://arxiv.org/html/2011.05297v1).

Ссылки ниже ведут на те же открытые страницы. Циркуляр [MPEC 2026-TE6](https://minorplanetcenter.net/mpec/K26/K26TE6.html) инструменту недоступен. Дата подтверждения и обозначение проверены по ESA; прямую проверку текста MPC не заявлять.

## Таблица утверждений

| Файл / место | Утверждение | Вердикт OK / исправить / убрать | Как должно быть / граница | URL |
|---|---|---|---|---|
| facts F01; script 0.25 | Миссия картографирует тёмную Вселенную | OK | Хук соответствует цели миссии; нет заявления о прямой фотографии тёмной материи. | [E5](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Top_five_mysteries_Euclid_will_help_solve) |
| facts F02; script 6.7, 12.0; shots v2 | Неподвижный звёздный фон; движение даёт след за экспозицию | OK | Удерживается небесная система отсчёта. Это накопленный сигнал, а не физический светящийся стержень. | [C1](https://www.euclid-ec.org/euclids-first-comet-discovery/) |
| facts F03; system EXPOSURE_S; shots v2 | 560.52 с; 20.09.2026 | OK | Значение относится к конкретному длинному кадру. 9 мин 20.52 с — правильный пересчёт. | [E2](https://www.esa.int/ESA_Multimedia/Images/2026/10/Comet_C_2026_S1_Euclid_observations_in_context) |
| facts F04 | 17.09.2026; 00:41:07, 00:58:53, 01:16:39 UTC; по 560.52 с | OK | Метки и длительность опубликованной серии совпадают. Не объявлять метки началом экспозиции. | [E3](https://www.esa.int/ESA_Multimedia/Images/2026/10/Comet_C_2026_S1_Euclid_streaks_across_the_sky) |
| facts F05; script 16.25; shots v3 | Программа Pöntinen отметила вытянутый след | OK | Допустим общий поиск следов; конкретный классификатор не установлен. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F06; script 24.2 | Команда предсказала положение для других изображений | OK | Не приписывать телескопу самостоятельное перенаведение. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F06; system OBSERVATIONS, EXPOSURES, FIELDS; script 29.3; shots v4 | 16–24.09.2026; 16 экспозиций; 5 полей; 2–4 на поле | OK | Числа совпадают с примечанием 4 ESA. 5 полей не равны 5 снимкам. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F07; script 34.25; shots v5 | Кома — признак активности; пыль и газ | OK | Это интерпретация видимого облака. Не заявлен спектроскопический состав. | [E2](https://www.esa.int/ESA_Multimedia/Images/2026/10/Comet_C_2026_S1_Euclid_observations_in_context) |
| facts F08; shots v6 | Нет совпадения с каталогами известных комет и астероидов | OK | Проверяется именно кандидат. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| script 42.2; соответствующий en_cap | “It matched no known comet or asteroid.” | OK | Исправление принято и повторно проверено. Прежняя версия “No known object matched the catalogs” переворачивала субъект проверки. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F09; script 42.2; shots v6 | Передача в MPC и наземные наблюдения | OK | Последовательность отражена верно. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F10; system CONFIRMED; shots v6 | MPC подтвердил комету 08.10.2026 | OK | По ESA; не по непосредственно прочитанному циркуляру MPC. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F10; system OBJECT; script 51.2; shots v7 | C/2026 S1 (Euclid) | OK | Обозначение и название совпадают. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F11; system ANNOUNCED; shots v7 | Анонс 19.10.2026; первая новая комета Euclid | OK | Известные кометы миссия наблюдала раньше. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F12 | Около 1.3 млрд км от Земли | OK | Это округлённое расстояние из релиза; не от Солнца и не навсегда. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts F13 | 8 × 89.5 с; выравнивание по комете; маскирование; удаление фона | OK | 716 с суммарно. Обработка относится к презентационному композиту, не к установленному детектору открытия. | [E4](https://www.esa.int/ESA_Multimedia/Images/2026/10/A_composite_of_eight_Euclid_VIS_exposures_of_Comet_C_2026_S1_Euclid) |
| facts F14 | Геометрические признаки и moving-Gaussian PSF в StreakDet | OK | §4.1 подтверждает методику. Наличие статьи не доказывает применение пакета к этой комете; оговорка сохранена. | [P1](https://arxiv.org/html/2011.05297v1) |
| facts, research_notes: неизвестные параметры | Не заявлены размер ядра, скорость, точная орбита, межзвёздность | OK | Ограничения соблюдены в текущих сценарии и экранных текстах. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| facts: гипотезы и неизвестные | Не обещать перехват Comet Interceptor | OK | ESA прямо исключает эту комету из подходящих целей. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| publish: Titles, Description, Cross-post | След в изображениях помог открыть комету | OK | Названия и короткие описания не добавляют иных механизмов обнаружения. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| publish: Description | Даты наблюдений; 16 / 5; 560.52 с; 08.10 и 19.10.2026 | OK | Совпадают с таблицей выше; ссылки соответствуют утверждениям. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet), [E2](https://www.esa.int/ESA_Multimedia/Images/2026/10/Comet_C_2026_S1_Euclid_observations_in_context) |
| publish: Pinned comment | ПО → другие изображения → кома/каталоги → наземная проверка | OK | Корректное сжатие цепочки без нового физического утверждения. | [E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |
| publish: условности | Реконструкция, условные координаты, отсутствие измеренного ядра и конкретного AI | OK | Соответствует возможностям источников и текущему коду шотов. | Локальная сверка с facts/system/shots |
| publish: Planned master / Finalization | 59.5 с, 1080×1920, 60 fps | OK | Явно обозначены как план; фактический мастер ещё не измерен. | Локальные параметры episode/сценария; не результат QA |
| publish: Proposed publication | Три календарных дня; точная граница 72 часов зависит от часа анонса | OK | Исправление принято и повторно проверено. Час анонса ESA не указан; гарантии попадания в точные 72 часа больше нет. | [Дата анонса E1](https://www.esa.int/Science_Exploration/Space_Science/Euclid/Euclid_discovers_new_comet) |

## Проверка визуальных утверждений по коду

| Место | Вердикт | Вывод / требуемая граница |
|---|---|---|
| system.py, координаты и палитра | OK | Координаты условные; физических расстояний, скоростей и размеров ядра нет. Цвет — оформление схемы. |
| v1, v7: светлая полоса | OK | Это изображение детектора; утверждения о форме твёрдого ядра нет. |
| v2: точка и накопление | OK | Длительность анимации 6.1 с показывает 560.52 с: около ×91.9. Значение экспозиции не переносится на все 16 кадров. |
| v3: сканирующая полоса и рамка | OK | Есть подпись schematic. Пояснять в описании, что это условный экран, а не реальный интерфейс или луч Euclid. Никаких AI confidence / процентов нет. |
| v4: 5 карточек, 16 меток, титр 5 FIELDS | OK | Актуальный код показывает пять условных полей. По 22 фоновых источника на карточке — параметр схемы, не реальный подсчёт в кадрах ESA. Положения, масштаб и фон не выдаются за астрометрию. |
| v5: STAR / COMET, Diffuse coma, Dust + gas | OK | Схематическое сравнение для уже установленной кометы. Не внушать, что любая вытянутая форма автоматически комета; оговорка есть в facts. |
| v5: Bright center remains unresolved | OK | Сохраняет запрет на показ измеренного ядра. Это ограничение реконструкции, а не оценка размеров по кадрам ESA. |
| v6: условный каталог | OK | Нет вымышленных реальных названий или астрометрических данных. |
| v6, v7: даты | OK | Подтверждение и анонс разведены правильно; ни одна дата не названа датой первого кадра открытия. |

## Исправления и условия следующей проверки

1. Фраза и en_cap при 42.2 с исправлены. После генерации речи проверить длительность реплики и синхронизацию; сейчас звуковая проверка не выполнялась.
2. Утверждение о точном 72-часовом окне в `publish_en.md` исправлено. Статус DRAFT корректен: это подготовка, не заявление о готовом мастере. Даты/числа, ссылки и условности в полноценном DRAFT проверены.
3. Сохранять запрет на установленное применение StreakDet, AI или image subtraction. Первоисточник подтверждает ПО поиска движущихся объектов; техническая реализация именно этого открытия не установлена.

**Открытых «исправить/убрать»: нет.** Текущие сценарий, экранные тексты и публикационный DRAFT согласованы с facts.md и указанными первоисточниками. После рендера остаётся сверить фактические титры и мастер; это не проверялось по ещё не существующим кадрам.
