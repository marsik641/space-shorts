# ep007 — Enceladus · HOME SYSTEM

Только EN, 59.5 с, 3570 кадров, 1080×1920p60. Стадия: мастер и release готовы 22.10.2026, framecheck / QA PASS.
Камера, зумы и переходы R2 приняты; поверхность согласована по первому кадру surface_r3.md.
MP4 и раскадровка R2 сохраняют предыдущий материал поверхности.
Отдельная команда владельца получена: после сборки / QA отправить мастер в Telegram «Избранное»,
затем дать ep008 отмашку на видеопревью и его отправку туда же на согласование.
Прежняя пауза и запрет сообщения ep008 отменены новым поручением. Текущие шаги — STATUS.md и finish.md.

## Файлы

- facts.md / factcheck.md — первоисточники и независимая проверка.
- system.py — реальные параметры и экранные условности.
- shots_9x16.py —7шотов,CLIpreview/draft/timing/final/save.
- script_9x16.json —10сегментовEN,голосaf_heart×0.98.
- music_cues.json —си минор,своя гармония и ледяные тембры.
- episode.json —монтаж,субтитры и подписи.
- publish_en.md —готовый пакет текста и источников; онлайн-публикация не выполнялась.
- STATUS.md —этап и очередьGPUсep008.
- approval_r2.md — сценарий, раскадровка, условности и бюджет предыдущей поверхности R2.
- surface_r3.md — текущая правка рыхлого покрова и один первый кадр на согласование.
- validation_r2.md — проверки исправленного черновика, текста, переходов, петли и ETA.
- validation_final.md — итоговые метаданные, проверки кадров и SHA256 мастера.
- approval.md / validation.md — архив первого, отклонённого показа.

## Новые модули

`spacekit.bodies.enceladus`:
- build_globe(texture=...) —глобуспоCassiniPIA14937;
- build_terrain(texture=...,detail_texture=...,extent=(100,100),resolution=...) —адаптивная реконструкция южного полюса;
- height(x,y),stripe_x(y,offset) —геометрия в километрах;
- ice_grain(radius=...,seed=...) —увеличенная иллюстрация льдинки.
- build_rubble(...) —инстансы обломков, noise(...) —детерминированный непериодический рельеф.

`spacekit.fx.plumes.build_plumes(name,sources,height,width,count,seed,frame_end,time0,time1,density,axis)`
—разреженные рассеивающие конусы иGN-льдинки. Кинематическая иллюстрация,не газодинамика.
Параметры потока и макроразмеры не являются измерениями. Ключи вместо драйверов.

## Воспроизведение

Перед КАЖДЫМ Blender/TTS/музыкой проверить out/RENDER.lock и Get-Process blender.
Один Blender за раз. Примеры PowerShell из корня репозитория:

```powershell
& '.venv/Scripts/python.exe' tools/check_episode.py episodes/ep007_enceladus/episode.json
& 'D:/Blender/blender.exe' -b --factory-startup -P episodes/ep007_enceladus/shots_9x16.py -- v1 preview 1,100,200,300 pct=50 samples=16
& 'D:/Blender/blender.exe' -b --factory-startup -P episodes/ep007_enceladus/shots_9x16.py -- v1 draft
```

Черновые кадры R2 идут в out/ep007_enceladus/9x16/draft_r2/, финальные — в frames/.
Видеопревью сохраняет 59.5 с и тайминг звука: 540×960, 8 spp, 15 фаз движения/с.
Переходы v3→v4→v5 — приближением в геометрии сцены.
Служебные EVENT studio_handoff/ice_handoff отмечают ожидаемое исчезновение сложного фона для framecheck.
При обновлении музыкальных cue их не превращать в дополнительные удары возле уже существующих склеек:
`tools/cues.py ... --exclude v3:487-533 --exclude v4:331-398`.
Последний служебный кадр631шотаv7 совпадает сv1_f0001;вмонтажv7идёт630кадров.
Карта: assets/enceladus/README.md. Существующие модули spacekit не изменялись.
