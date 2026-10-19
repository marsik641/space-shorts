# Эп. 004 — кольца Сатурна (TRUE SCALE): факты и источники

Собрано 19.10.2026 (исследователь, `.claude/workflows.md`); все URL открыты при сборе. Википедия — только навигация.
Уверенность: высокая — измерение/каталог; средняя — модель, оценка, расчёт из измеренного; гипотеза — в тексте may/might.
Радиусы колец — по PDS Ring-Moon Systems Node (абсолютная шкала French et al. 2017); NSSDC местами расходится на
до 290 км (край A) — в ролике числа округлены так, что расхождение не важно.

Короткие имена источников:
- **NSSDC-R** — https://nssdc.gsfc.nasa.gov/planetary/factsheet/satringfact.html
- **NSSDC-S** — https://nssdc.gsfc.nasa.gov/planetary/factsheet/saturnfact.html
- **NSSDC-M** — https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html
- **PDS** — https://pds-rings.seti.org/saturn/saturn_tables.html
- **JPL-sat** — https://ssd.jpl.nasa.gov/sats/phys_par/
- **NASA-facts** — https://science.nasa.gov/saturn/facts/
- **NASA-rings** — https://science.nasa.gov/mission/cassini/science/rings/
- **NASA-2018** — https://science.nasa.gov/solar-system/nasa-research-reveals-saturn-is-losing-its-rings-at-worst-case-scenario-rate
- **Ohtsuki25** — Ohtsuki K. (2025), «Rings around giant planets and smaller bodies», Encyclopedia of Astrophysics,
  https://arxiv.org/html/2508.11963v1
- **Iess19** — Iess et al. (2019), Science 364, eaat2965, doi:10.1126/science.aat2965 — таблица 1:
  https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/Cassini/logs/Iess-Science-2019.pdf

## Факты в ролике

| Факт в ролике | Значение | Источник (URL) | Уверенность |
|---|---|---|---|
| «about ten meters thick» | NASA: «generally about 30 feet (10 meters) thick or so»; «vertical height is typically about 30 feet (10 meters) in the main rings»; Ohtsuki: «typically about 10 m thick»; NSSDC по кольцам: C 5 м, B 5–10, A 10–30 м | NASA-rings; NASA-facts; Ohtsuki25; NSSDC-R | средняя (модель; есть волны и структуры до 2,5–4 км — PIA11668, PIA11677) |
| «270,000 km across» | внешний край A — 136 780 км (NSSDC) / 136 770 (PDS) → диаметр **273 560 км** | NSSDC-R; PDS | высокая |
| «70 % of the gap» Земля–Луна | 273 560 / 384 400 = **0,71**; Ohtsuki: «about 70% of the distance from the Earth to the Moon» | NSSDC-M; Ohtsuki25 | высокая |
| «paper … almost 3 km across» | толщина/диаметр = 10 м / 273 560 км = 3,66·10⁻⁸; лист 0,1 мм в той же пропорции — диск **2,74 км** (0,103 мм — 2,82 км); толщина офисной бумаги ~0,1 мм | расчёт; https://hypertextbook.com/facts/2001/JuliaSherlis.shtml | средняя (от «10 м») |
| «they split into ringlets and gaps, one kept open by a moon just 28 km wide» | ringlet'ы и щели C, деления Кассини и A — PDS (Titan, Maxwell, Huygens ringlet; щели Colombo, Maxwell, Huygens, Encke, Keeler…); NASA: Пан «responsible for keeping the Encke Gap open», средний радиус **14,1 км** → ~28 км; полуоси ~17×16×10 км (Thomas et al. 2018) | https://science.nasa.gov/saturn/moons/pan/ ; PDS | высокая |
| «countless chunks of almost pure water ice» | NASA: «almost completely composed of billions (if not trillions) of chunks of water ice»; обзор: «strongly dominated by water ice» (Miller et al. 2024, SSR 220:70, doi:10.1007/s11214-024-01104-y). Процент льда не называем | NASA-rings | высокая |
| «from specks of dust to blocks as big as a house» | NASA: «from tiny, dust-sized icy grains to chunks as big as a house»; Marouf et al. 1983: распределение обрывается на ~4–5 м (радиус); Ohtsuki: «a few centimeters to 10 m» | NASA-facts; https://ntrs.nasa.gov/citations/19830054510 ; Ohtsuki25 | высокая |
| «Out here … about 60,000 km an hour» (кольцо A, v4) | v = √(GM/r), GM = 37 931 206,23 км³/с² (JPL SAT441): A — 17,6 → 16,7 км/с = **63 500 → 59 900 км/ч**; место шота v4 — 128 000 км: 17,2 км/с = 62 000 км/ч | JPL-sat (GM); расчёт | высокая |
| «neighbors drift past at a snail's pace: millimeters per second» | Ohtsuki: относительные скорости «typically on the order of mm s-1 or even smaller (Salo 1995; Ohtsuki et al. 2020)»; проверка c ≈ HΩ = 1,3 мм/с (A, H = 10 м); садовая улитка ~1 м/ч ≈ 0,28 мм/с (Univ. of Exeter, 2013) | Ohtsuki25; https://news-archive.exeter.ac.uk/2013/august/title_315519_en.html | средняя (модели N тел; сравнение — по порядку величины) |
| «Crush all that ice into one ball: about 320 km wide» | масса колец (1,54 ± 0,49)·10¹⁹ кг (Iess19); лёд 917 кг/м³ → D = **318 км** (±1σ массы: 280–348 км; +2σ — 374 км); при пористости 0,5 — ~400 км | Iess19; плотность льда: https://www.engineeringtoolbox.com/ice-thermal-properties-d_576.html ; расчёт | средняя (зависит от пористости; показываем плотный лёд) |
| «smaller than Saturn's little moon Mimas» | Мимас: средний радиус 198,20 км → **D = 396,4 км** (JPL; NASA — 394 км); масса колец = 0,41 ± 0,13 массы Мимаса (Iess19) | JPL-sat; https://science.nasa.gov/saturn/moons/mimas/ ; Iess19 | высокая |
| Кратер Гершель (в кадре v5, без числа) | «80 miles (130 kilometers) across — one third of the diameter of the moon» | https://science.nasa.gov/saturn/moons/mimas/ | высокая |
| «raining onto Saturn: an Olympic pool's worth every half hour» | NASA: «drains an amount of water products that could fill an Olympic-sized swimming pool from Saturn's rings in half an hour» (≈1 390 кг/с — внутри 432–2 870 кг/с, O'Donoghue et al. 2019, Icarus 322:251) | NASA-2018; https://reading-pure-test.eprints-hosting.org/120084/1/odonoghue_et_al_2018.pdf | средняя |
| «In a few hundred million years, the rings may be gone» | NASA: «the entire ring system will be gone in 300 million years»; O'Donoghue: 292 (+818/−124) млн лет только «дождём»; с экваториальным притоком (Cassini Grand Finale) — «less than 100 million years to live» | NASA-2018; O'Donoghue 2019 | гипотеза/экстраполяция → «may» |

## Данные сцены (в кадре, без озвучки)

| Что | Значение | Источник | Уверенность |
|---|---|---|---|
| Сатурн: R экв / пол (1 бар), сжатие | 60 268 / 54 364 км, f = 0,09796 | NSSDC-S | высокая |
| Вращение | 10 ч 33 мин 38 с (Mankovich et al. 2019, ApJ 871:1, https://arxiv.org/abs/1805.10286); System III 10,656 ч | NSSDC-S | средняя |
| Шестиугольник | ~77° с. ш., поперечник ~30 000 км | https://www.jpl.nasa.gov/news/saturns-mysterious-hexagon-emerges-from-winter-darkness/ ; NASA-facts | высокая |
| Края колец, км | D 66 900; C 74 491; B 91 975–117 570; деление Кассини 117 500–122 050; A 122 050–136 770; Энке 133 423–133 745; Килер 136 487–136 522; F 139 826–140 612 (ядро 140 224) | PDS | высокая |
| Оптическая толщина | C 0,05–0,35; B 0,4–5 (B3 — 3,6); деление Кассини 0–0,2; A 0,4–1,0; F 0,01–0,2 | PDS; NSSDC-R | высокая |
| Альбедо частиц, цвет | C 0,12–0,30; B, A 0,4–0,6; кольца бледно-бежевые, красноватые; C и деление Кассини «грязнее» | NSSDC-R; Cuzzi, AGU 2014: https://ntrs.nasa.gov/api/citations/20190027592/downloads/20190027592.pdf | высокая |
| Распределение размеров | n(a) ∝ a⁻³ (q ≈ 3) от см до ~5 м | Brilliantov et al. 2015, PNAS 112:9536, doi:10.1073/pnas.1503957112; Marouf 1983 | высокая |
| Гравитационные «следы» в кольце A | вытянутые сгущения, шаг ~50–100 м | Ohtsuki25 (λ_cr = 4π²GΣ/Ω² ≈ 46–61 м) | средняя (модель; на снимках не разрешены) |
| Мимас: орбита | a = 185 539 км, наклон 1,57°; приливный захват | JPL https://ssd.jpl.nasa.gov/sats/elem/ | высокая |
| Земля, Луна | R 6 371 / 1 737,4 км; Земля–Луна 384 400 км | NSSDC-M | высокая |

## Условности (в описание ролика)

- **Толщина с ребра.** 10 м при диаметре колец на весь кадр — 4·10⁻⁵ пикселя: линия колец с ребра (хук и петля) —
  проекция диска под углом ~0,16°, а не «настоящая» толщина; в рендере ровно в плоскости кольца исчезают совсем
  (настоящие оставались бы тончайшей линией и тенью на планете).
- **Освещение — эпохи Cassini:** Солнце над северной стороной колец (2009–2025; угол рос от 0° до 26,7° к солнцестоянию
  24.05.2017) — у нас 15°, как около 2012 г. В октябре 2026 г. Солнце освещает южную сторону под ~8° (с 06.05.2025),
  с Земли кольца — узкий эллипс ~7°.
- **Мелкая структура колец** (ringlet'ы, волны плотности, неоднородность кольца B) — процедурная поверх реальных границ
  и оптической толщины PDS; деление Кассини не пустое (τ до 0,2) — так и показано, без чёрной щели.
- **Поле частиц (v4)** — модель (вне ~1 км — плоскость с той же оптикой, что кольцо): степенной закон размеров, нормировка на τ ≈ 0,6, «следы» кольца A, форма комьев
  условная (реальные частицы не снимал ни один аппарат); пыли и частиц мельче 3 см нет, мелкие — только у камеры.
  Частицы неподвижны: относительные скорости — мм/с.
- **Камера** летит быстрее любых частиц (v3: до ~4 000 км/с) — это пролёт камеры, а не движение колец.
- **Пан (v3)** — эллипсоид без экваториального хребта (на экране ~11 px), положение по азимуту условное.
- **Земля и Луна (v2)** поставлены рядом с кольцами для масштаба; размеры и расстояние — реальные.
- **Шар льда (v5)** — мысленный эксперимент: вся масса колец (Iess 2019) плотным льдом 917 кг/м³ — 318 км (по ошибке
  массы 280–348 км); с пористостью — крупнее. Поставлен рядом с Мимасом для сравнения.
- Цвета колец и полос Сатурна — по снимкам в естественных цветах, контраст художественный.

## Гипотезы (в тексте — may/might)

- Исчезновение колец через «несколько сотен миллионов лет» — экстраполяция нынешнего «дождя» (NASA 2018; O'Donoghue 2019)
  → «may be gone».
- Возраст колец не называем: от 10–100 млн лет (Iess 2019) и ≲400 млн лет (Kempf et al. 2023, Sci. Adv. 9, eadf8537) до
  возможно ~4,5 млрд лет (Hyodo, Genda & Madeira 2025, Nat. Geosci. 18:44).
