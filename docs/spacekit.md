# spacekit: что умеет и шпаргалка API

Библиотека сцен (импорт внутри Blender 5.2, `sys.path` → корень репо). Версия 0.1.0, ≈ 4600 строк (эп. 002 добавил аппарат, траектории, подписи, кольца).
Перед оценкой темы в `/next-video` — сверить с матрицей ниже: всё, что «нет», — новый модуль (часы работы + регресс эп. 001).

## 1. Матрица возможностей

| Область | Есть | Нет / ограничения |
|---|---|---|
| **Нейтронная звезда** | `bodies.neutron_star`: поверхность, 2 объёмных луча, прожекторы вдоль лучей, точечный свет, линии дипольного поля, частицы, вспышка при проходе луча через камеру | Второй пульсар в одной сцене: имена объектов/материалов фиксированы (`PSR_*`, `C.new_material` берёт материал по имени) → материалы и вспышки общие. Магнитар: «звёздотрясение», гигантская вспышка, сильное поле — нет |
| **Планеты** | `bodies.planets.build_planet`: процедурная поверхность, атмосфера (аналитическая оболочка), сияния, LOD close/mid/far, суточное вращение, наклон оси | `kind` только `draugr`, `poltergeist`, `phobetor` (планеты PSR B1257+12). Газовый гигант с полосами, раскалённая/лавовая, ледяная, «алмазная», океан, кольца планеты, приливная деформация, облака — нет |
| **Звёзды (тела)** | Свет: `lighting.add_point_star` (точечный, цвет чёрного тела); `lighting.add_distant_sun` — параллельный свет + точка-звезда с ореолом (Солнце издалека) | Видимый диск звезды (фотосфера, лимб, пятна, корона), красный карлик, гигант, белый карлик, звезда-компаньон с испарением — нет |
| **Чёрные дыры** | — | Горизонт, аккреционный диск, гравлинзирование, джеты — нет (серия BLACK HOLES требует нового модуля) |
| **Туманности / облака** | — | Объёмная туманность (Краб), волокна, остаток сверхновой — нет |
| **Скопления** | Звёздное поле на «бесконечности» (`sky.build_starfield`) | Шаровое скопление как объект в сцене (Terzan 5) — нет |
| **Потоки вещества** | Частицы вдоль лучей пульсара (внутри `neutron_star`) | Поток с компаньона, хвост кометы, ветер, испарение атмосферы — нет |
| **Аппараты / малые тела** | `bodies.voyager`: процедурный Voyager 1/2 (тарелка 3.66 м с контррефлектором, шина-десятигранник, РИТЭГи, научная штанга со сканплатформой, магнитометр 13 м, антенны PWS, Золотая пластинка с гравировкой) | DART, другие аппараты, астероид/двойной астероид, ядро кометы, луна неправильной формы — нет |
| **Эффекты** | `fx.dust_ring`: пылевое кольцо с аналитическим освещением и дугами от прожекторов; `fx.orbit_line`: светящиеся линии орбит со следом (+ `key_screen_width`); `fx.path_line`: линия по точкам (траектории по данным) с прорисовкой во времени и постоянной экранной толщиной (GN); `fx.shell`: оболочка-граница (сфера/лист с волокнами) и кольцо-силуэт к камере (фронт сигнала, гелиопауза); `fx.label`: 3D-подписи постоянного кегля | Гравволны, ударные волны, взрывы, вспышки сверхновой — нет |
| **Небо** | Млечный Путь (HDR, пыль), звёзды point cloud (до 300 тыс., блеск по величинам), ориентация галактики под кадр или реальная (`galactic_to_world`, матрица `A_ICRS_GAL`), одинаковое небо при разной экспозиции; реальные яркие звёзды по каталогу (`catalog=BRIGHT_ORION` — Орион и соседи) | Полный каталог звёзд (сейчас — только окрестности Ориона), вид неба с конкретной планеты — нет |
| **Орбиты** | Круговые (`add_orbit`), кеплеровские эллипсы (`add_kepler_orbit`), законы Кеплера, сжатие периодов (`video_periods`), положение на орбите заранее | `add_kepler_orbit`: порядок поворотов исправлен (Rz(node)·Rx(incl), проверено), в роликах ещё не обкатана. N-body, приливы — нет |
| **Камера** | Rig камера+цель, ключи пути (Bezier), сферические координаты, кадрирование тела и звезды (`frame_two_subjects`), ось пульсара под цель (`tilt_for_target`) | Тряска, автофокус/DOF-хелперы, follow-cam по орбите — нет (писать ключами) |
| **Рендер** | 16:9 / 9:16, Cycles/OptiX, AgX, блум + Fog Glow, слой звёзд без денойза, денойз под шот, PNG-секвенции с докачкой | Видео напрямую, HDR — нет |
| **Обвязка шотов** | `shot.base_scene/finish/run`, CLI `preview/final/save/pct/samples/outdir`, `report_flash` | Общего `report_events` нет — печатать вручную `EVENT <шот> <имя>: кадр[:v], …` (для `tools/cues.py`) |

Темы `docs/channel.md` → что нужно (по именам): ✅ Voyager 1 (эп. 002); DART/Диморф — модель аппарата, астероид; Энцелад, Ио,
кольца Сатурна, «Сатурн на месте Луны» — новые kind лун/гиганта с кольцами; Фобос → кольцо — приливное разрушение;
Шумейкер — Леви 9 — фрагменты кометы, вспышки ударов; Андромеда и Млечный Путь — галактики (частицы/объём);
J1748 — скопление; J0952 — звезда-компаньон + поток; SGR 1806 — магнитар/вспышка; Краб — туманность; двойной
пульсар — префикс имён в `build_pulsar`; J1719 b — новый kind планеты; Sgr A* — чёрная дыра + линзирование;
TRAPPIST-1 — диск красного карлика + 7 kind планет; KELT-9b, WASP-12b, HD 189733b, TrES-2b — диск звезды + новые kind;
GW150914 — две ЧД + волны; 3I/ATLAS — кома/хвост.

**Объём существующих модулей** (ориентир трудоёмкости; часы не записывались): neutron_star 690 строк,
planets 1025 (3 kind ≈ 80–150 строк материала на kind), dust_ring 350, sky 540, render 210, camera 110, orbits 115.

## 2. Шпаргалка API

Импорт в скрипте шота: `from spacekit import core as C, camera as CAM, shot as S, sky as SKY, orbits as ORB, lighting as LT`,
`from spacekit.bodies import neutron_star as NS, planets as PL`, `from spacekit.fx import dust_ring as DR`.

### Обвязка шота (`shot`)

```python
S.OPT.update(fmt="9x16", fps=60)                       # до base_scene
sc = S.base_scene(n, exposure=0.0, samples=40, adaptive=0.03, bloom_strength=0.6)   # fmt/fps — из OPT
...  # объекты сцены, камера, небо
S.finish(sc, stars, denoise="close"|"far", star_samples=24)    # ПОСЛЕ всех объектов
S.report_flash("v1", NS.key_pulse_flash(psr, cam, 1, n))      # строка FLASH для tools/cues.py
S.run(BUILDERS, out_dir=OUT, render_end={"v2": 314})          # CLI
```
CLI: `-- <шот> [preview F1,F2,..] [pct=50] [samples=N] [outdir=DIR] [final] [save]`. Превью — `<out_dir>/previews/<шот>_fNNNN.png`,
финал — `<out_dir>/frames/<шот>/####.png` (докачка), save — `<out_dir>/scenes/<шот>.blend`. fps брать из сцены
(`C.scene_fps(sc)`), не из `S.OPT`, если шот переопределяет fps.

### Пульсар (`bodies.neutron_star`)

`build_pulsar(scene, *, location, tilt_euler, R=1.0, alpha_deg=78, spin_hz=0.6, phase0_deg=0, frame_start, frame_end,
beam_length=40, beam_half_angle_deg=8, beam_intensity=1.0, light_energy=20000, spot_energy=None (4×light),
detail="close"|"far", field_lines=True, particles=True, surface_strength=None, field_strength=1.0, seed=0)`
→ dict `root, spin, mag, surface, beams[N,S], spots[N,S], light, field_lines, particles, mats, params`.
- `root.rotation` = ось вращения (Z root), `alpha_deg` — угол магнитной оси к оси вращения; `spin_hz` — экранная
  частота (реальную замедлять, масштаб — в docstring `system.py`).
- `detail="far"` — точка без линий поля/частиц; планета на ~40 ед.: `light_energy` 6000–8000, `spot_energy` ≈ 3×.
- `key_pulse_flash(objs, camera, frame_start, frame_end, width_deg=None (1.6·half_angle), substeps=4, gamma=0.7,
  light_gain=0.0)` → пики `[(кадр, v>0.05)]`; вызывать во всех шотах, где луч может пройти через камеру. Окно выдержки
  зашито 0.5 (при shutter 0.3–0.4 вспышка чуть шире). Перекрытие телами не учитывает.
- `beam_axes_world(objs, frame)`, `beam_frame_for_azimuth(objs, az_deg, after_frame)` — когда луч смотрит в нужную сторону.

### Планеты (`bodies.planets`)

`build_planet(scene, kind, *, radius=1.0, location, parent=None, detail="close"|"mid"|"far", seed=0, axial_tilt_deg=None,
rot_period_s=None, frame_start, frame_end, aurora_strength=1.0, light=None, name=None, tilt_azimuth_deg=0, mag_offset_deg=10)`
→ dict `root, planet, atmosphere, aurora, aurora_shells, sunref, materials, kind, radius`. На орбиту ставится `root`.
- `detail`: close — планета ≥ 25 % высоты кадра; mid — < 25 %; far — точка/диск без сияний.
- Свет — только от лампы (`light`, по умолчанию первая точечная): `set_sun(objs, light, energy, color)`,
  без лампы — `set_sun_dir(objs, direction, irradiance=4.0)`. Атмосфера под вспышки/прожекторы:
  `key_sun_power(objs, psr, f0, f1)` — ПОСЛЕ `add_orbit`.
- **Ограничение KINDS:** только `draugr` (тёмная кратерная), `poltergeist` (рифты, тонкая атмосфера, сияния),
  `phobetor` (плотная дымка, сияния). Как добавить kind:
  1. `KINDS["<kind>"] = dict(tilt=…, rot=…, aurora=bool, atmo=None | dict(H, tau=(r,g,b), mie, g, tw, tail))`;
  2. функция `_mat_<kind>(name, seed, radius, lod)` → материал (база `_surface_base`, шумы `_nz` с LOD, кратеры
     `_crater_layers`, финал `_finish`); `lod` 0/1/2 убирает мелкие детали;
  3. `SURFACE["<kind>"] = _mat_<kind>`;
  4. превью close/mid/far + регресс эп. 001 (`tools/imgdiff.py`) — старые kind не должны измениться.

### Орбиты (`orbits`)

- `video_periods({"b": 25.3, "c": 66.5}, ref="b", ref_seconds=20.0)` → периоды в секундах ролика (отношения честные).
- `add_orbit(scene, body, *, center_parent, a, period_s, phase_deg=0, frame_start, frame_end, incl_deg=0, inertial_axis=True)`
  → пивот; круговая, ключи LINEAR; ось планеты не прецессирует.
- `add_kepler_orbit(scene, body, *, center_parent, a, e, period_s, phase_deg=0 (средняя аномалия), omega_deg=0,
  incl_deg=0, node_deg=0, frame_start, frame_end, step=1)` → плоскость; ключи положения по кадрам. `node_deg` — пока 0.
- `kepler_period_days(a_au, m_msun)`, `kepler_a_au(P_days, m_msun)`, `position_on_orbit(a, period_s, phase_deg, t_s, e, omega_deg)`
  — где будет тело в момент t (для кадрирования заранее).

### Камера (`camera`)

- `sph(dist, az_deg, el_deg, center)` — точка в сферических координатах.
- `camera_rig(name, lens=35, clip_start=0.05, clip_end=1e6, sensor_fit="AUTO")` → `(cam, tgt)`; sensor 36 мм по БОЛЬШЕЙ
  стороне: в 9:16 35 мм дают тот же угол по высоте, что в 16:9 по ширине.
- `key_camera(cam, tgt, [dict(frame, loc, target, lens?)], ipo="BEZIER")` — после последнего ключа камера стоит.
- `frame_two_subjects(subject_far, phase_deg, dist, up_deg, w_near=0.56, drop_deg=3, center)` → `(dict(loc, target), look)`:
  тело в center и звезда в одном кадре; phase 180° — серп, 90° — полуфаза; угол между ними в кадре ≈ 180° − phase.
- `tilt_for_target(src_loc, target, alpha_deg)` → Euler для `root` пульсара: луч раз за оборот проходит через target
  (камеру/планету).

### Небо (`sky`)

- `build_sky(sc, cam, exposure, ref_exposure=0.4, mw_strength=0.45, gal=GAL_EULER, star_brightness=1.0, mag_limit=10)`
  → объект звёзд (в `S.finish`). Вызывать после `base_scene` и камеры; компенсирует экспозицию шота.
- `gal_for_view(view_dir, tilt_deg=30, l_center_deg=15)` → Euler галактики: полоса под углом tilt к горизонту кадра;
  `l_center` 0 — балдж с пылью, 60–120 — спокойная полоса, 180 — тускло.
- При смене объектива/процента после постройки — `update_starfield(sc, stars, camera, lens)`.

### Пылевое кольцо (`fx.dust_ring`)

`build_dust_ring(scene, parent, inner=48, outer=72, thickness=6, density=1.0, seed=1, anisotropy=0.6, color,
rotation_period_s=None, frame_start, frame_end, lights=None, mode="emission"|"scatter", flare=1.3, tilt_deg=4,
ring_radiance=4.0, arc_gain=3.0, arc_sigma=0.6, arc_cone=0.4, biased=True)` — вызывать после пульсара (лампы читаются
в момент вызова). `emission` — без шума, яркость не зависит от мощности ламп (`ring_radiance`); `scatter` — честный
объём, ~20 с/кадр. Ставит `volume_biased`.

### Линии орбит (`fx.orbit_line`)

`build_orbit_line(name, a, e=0, parent=None, incl_deg=0, node_deg=0, omega_deg=0, width=0.006, color, strength=6,
trail_head_deg=0, trail_len_deg=0, floor=0.06)` — эллипс-кривая (фокус в начале координат родителя, поворот
Rz(node)·Rx(incl), как `orbits.add_kepler_orbit`), эмиссия + прозрачность; `trail_len_deg>0` — след гаснет назад от
головы (угол головы — истинная аномалия; для e=0 совпадает со средней). `key_trail(ob, deg0, deg1, f0, f1)` —
бегущий след, `point_on_orbit(a, e, M_deg)` — куда ставить тело. Не освещает сцену и не отбрасывает тени.
Пример — `tools/brand.py` (оформление Orbitfall).

### Voyager (`bodies.voyager`)

`build_voyager(scene, *, location=(0,0,0), detail="close"|"far", name="Voyager", parent=None)` → dict `root, parts{dish,
dish_parts, bus, bus_parts, rtg, sci, mag, pws, record}, mats, z_dish, dims`. 1 ед. = 1 м, +Z модели — ось тарелки.
`aim(vg, direction, roll_deg=0)` — тарелку на Землю; `world_point(vg, local)` — точка модели в мир (камеры у деталей).
Азимуты штанг/граней: `AZ_RTG`, `AZ_SCI`, `AZ_MAG`, `AZ_RECORD` (грани шины — каждые 36° от 0°). Шина в тени тарелки
(Солнце на оси) — для крупных планов нужен заполняющий свет или софтбокс на камере (условность, писать в описании).

### Далёкое Солнце (`lighting.add_distant_sun`)

`add_distant_sun(name, direction, strength=3.0, temp_k=5772, angle_deg=0.05, star_dist=5e4, star_radius=None,
star_strength=4e3)` → (лампа SUN, сфера-звезда). Сферу передавать в `S.finish(sc, [stars, disk])` — в слой звёзд без
денойза (иначе субпиксельную звезду съест OptiX); ореол даёт блум. Тени и свет на сцену — только от лампы.

### Экранные размеры (`fx.label.pixel_angle`)

Все «пиксельные» размеры (кегль подписей, толщины линий/колец, радиусы точек) — в пикселях итогового кадра 100 %:
превью pct=50 показывает те же пропорции, что финал.

### Линия по точкам (`fx.path_line`)

`build_path_line(name, points, color, strength, t=None, head=1.0, trail=0.2, floor=0.25, parent=None, cam=None, px=1.2,
width=0.01)` — трубка с атрибутом `t` (доля длины или свой параметр, например дата); видна часть `t ≤ head`, у головы
ярче. `cam=` — постоянная экранная толщина (GN по расстоянию каждой вершины до камеры). `key_head(ob, h0, h1, f0, f1)` —
прорисовка; `key_follow(ob, points, h0, h1, f0, f1, t=)` — объект-голова; `point_at(points, frac, t)`. Замкнутую
орбиту строить так же (точки по элементам + замыкание) — толщина не «раздувается» у камеры, в отличие от `orbit_line`.

### Оболочки и кольца (`fx.shell`)

`build_shell(name, radius, color, strength, rim_power, noise_scale, …)` / `build_sheet(...)` — светящаяся граница
(Layer Weight × волокна шума, без объёма); `key_strength`, `key_flow`, `key_radius(ob, r_of_frame, f0, f1)`.
`build_ring(name, cam, radius, color, strength, fill, fill_power)` + `key_ring(ob, cam, r_of_frame, px, f0, f1)` —
силуэт сферы кольцом, всегда параллельным кадру: фронт света (радиус по любой шкале времени), граница гелиосферы на
схеме. Близкая камера + сфера = «планета с атмосферой» — для схем брать кольцо. Чтобы кольцо в перспективе проходило
через точку P, радиус считать покадрово: пересечение луча камера→P с плоскостью кольца (пример — ep002 v4).

### Подписи (`fx.label`)

`build_label(name, text, location, cam, px=32, offset_px=(0,0), color, strength, font=None (FONT), align, parent)` —
FONT-объект, Copy Rotation от камеры; `key_screen_size(lb, cam, f0, f1, step)` — постоянный кегль при движении камеры;
`key_fade(lb, peak, f_in, f_out, length)`. `LB.FONT` — шрифт по умолчанию (в Bahnschrift нет стрелок и «≈»).
Подписи к телам, которые в момент события вне кадра, не работают — такие списки делать титрами монтажа.

### Свет (`lighting`)

- `point_energy_for(irradiance, distance)` / `point_irradiance(energy, distance)` — калибровка: белый диффуз под
  точечным светом = 0.0303·P/d². Тёмная планета читается при irradiance 4–6, светлая ледяная — 2–3.
- `add_point_star(name, energy, temp_k=6000, radius=0.3, location, parent)` — точечная «звезда» с цветом чёрного тела.
- `blackbody_rgb(T)`, `spot_factor(spot, target)`.

### Рендер и прочее

- `render.FORMATS` `16x9`/`9x16`; `setup_cycles`, `setup_color`, `setup_compositor`, `setup_star_layer`,
  `setup_volume_denoise(sc, "close"|"far")` — обычно через `S.base_scene`/`S.finish`.
- `anim.key_rot_z(ob, z0, deg_per_s, f0, f1)`, `anim.set_interpolation(id, ipo, extrapolate, path_contains)` — f-кривые
  Blender 5 (слоты). Анимация только ключами: Python-драйверы в фоне не работают.
- `core`: `reset_scene`, `collection`, `link`, `empty`, `new_material` (get-or-create по имени!), `math_node`, `scene_fps`.
