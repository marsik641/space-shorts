"""spacekit — библиотека сцен для научных космических визуализаций (Blender 5.2, Cycles/OptiX).

Импорт из скрипта, запущенного `blender -b --factory-startup -P script.py -- ...`:

    import os, sys
    sys.path.insert(0, <корень репозитория>)
    from spacekit import core, render, camera, anim, orbits, lighting, sky
    from spacekit.bodies import neutron_star, planets
    from spacekit.fx import dust_ring

Модули:
    core      — сцена, коллекции, empty, материалы, math-узлы, пути репозитория
    render    — форматы кадра (16:9 / 9:16, fps), Cycles/OptiX, AgX, компоузер (блум), слой звёзд, рендер
    camera    — камера + цель (Track To), ключи пути, сферические координаты, кадрирование двух объектов
    anim      — f-кривые Blender 5 (слоты/каналбэги), LINEAR/BEZIER, равномерное вращение
    orbits    — круговые и кеплеровские (эллиптические) орбиты, масштабирование реальных периодов в секунды ролика
    lighting  — цвет чёрного тела, калибровка освещённости точечного света, доля мощности прожектора
    sky       — звёздное поле (point cloud) и Млечный Путь (HDR), ориентация галактики под кадр
    bodies/   — neutron_star (пульсар: поверхность, лучи, линии поля, вспышки), planets (процедурные планеты, атмосфера, сияния)
    fx/       — dust_ring (пылевое кольцо с аналитическим освещением лучами)
"""
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
__version__ = "0.1.0"
