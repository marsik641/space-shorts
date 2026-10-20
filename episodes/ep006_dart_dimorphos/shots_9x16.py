"""Эп006 DART: 42с / 2520 кадров, шесть кинематографичных сцен.
1) аппарат и каменная цель; 2) пролёт вдоль крыла к MLI-корпусу;
3) контакт/выброс; 4) боковой вид отдачи; 5) орбита в масштабе;
6) реприза аппарата: кадр481 = кадр1 v1, одинаковая скорость на шве.
Время подлёта/выброса замедлено, v5 ускорено; 1ед=1м.
CLI: -- vN preview 1,120,... pct=50 | final | save.
"""
import math
import os
import sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.abspath(os.path.join(HERE,'..','..')))
sys.path.insert(0,HERE)
import bpy
from mathutils import Vector
from spacekit import anim as A, camera as CAM, core as C, lighting as LT, orbits as ORB, shot as S, sky as SKY
from spacekit.bodies import asteroid as AST, dart as DT
from spacekit.fx import impact as IMP, path_line as PLN, label as LB
import system as SY
EP=os.path.basename(HERE)
OUT=os.path.join(C.OUT,EP,'9x16')
STONE_TEXTURE=os.path.join(C.ASSETS,'dart','stone_albedo_v1.png')
S.OPT.update(fmt='9x16',fps=60)
SHOTS={'v1':300,'v2':360,'v3':420,'v4':420,'v5':540,'v6':481}
LB.FONT='C:/Windows/Fonts/bahnschrift.ttf'


def base(n,samples=40,ex=1.1):
    sc=S.base_scene(n,exposure=ex,samples=samples,adaptive=.025,
                    look='None',bloom_strength=.35)
    sc.cycles.diffuse_bounces=2
    sc.cycles.glossy_bounces=3
    sc.render.motion_blur_shutter=.35
    LT.add_distant_sun('DART_Sun',SY.SUN_DIR,strength=3.2,temp_k=5772,
                       angle_deg=.5,star_dist=45000,star_strength=35)
    return sc


def finish(sc,cam,n,ex=1.1):
    sc.frame_set(1)
    cam.data.clip_end=3000000
    bpy.context.view_layer.update()
    view=cam.matrix_world.to_quaternion() @ Vector((0,0,-1))
    # Тот же sky и пресет, что у ep004/v1: стандартные MW, плотность и блеск.
    stars=SKY.build_sky(sc,cam,ex,
                      gal=SKY.gal_for_view(view,tilt_deg=-35,l_center_deg=70),
                      star_brightness=.8)
    S.finish(sc,stars,denoise='far',star_samples=32)
    return sc,n


def keycam(cam,tgt,n,fn,step=4):
    frames=sorted(set(range(1,n+1,step))|{n})
    for f in frames:
        loc,target=fn(f)
        cam.location=loc; cam.keyframe_insert('location',frame=f)
        tgt.location=target; tgt.keyframe_insert('location',frame=f)
    A.set_interpolation(cam,'LINEAR',extrapolate='LINEAR')
    A.set_interpolation(tgt,'LINEAR',extrapolate='LINEAR')


def dimorphos(detail='close',rocks=4200):
    return AST.build_asteroid('Dimorphos',radius=SY.DIMORPHOS_R,axes=SY.DIMORPHOS_AXES,
                             seed=SY.SEED,detail=detail,boulder_count=rocks,texture=STONE_TEXTURE)


def spacecraft(pos,detail='close'):
    d=DT.build_dart('DART',location=pos,detail=detail)
    d['root'].rotation_mode='QUATERNION'
    d['root'].rotation_quaternion=Vector((0,0,1)).rotation_difference(Vector((0,1,0)))
    # ROSA поворачиваются к солнечному свету независимо от направления DRACO.
    wing_pivot=C.empty('DART_SolarPivot',coll='DART',parent=d['root'])
    for ob in list(d['root'].children):
        if '_ROSA_' in ob.name:
            ob.parent=wing_pivot
    wing_pivot.rotation_euler.x=math.radians(135)
    # Прокси отражённого от освещённой поверхности Диморфа солнечного света.
    # Большая слабая площадка улучшает сходимость того же непрямого освещения.
    ld=bpy.data.lights.new('Dimorphos_Bounce','AREA')
    ld.energy=18000; ld.shape='DISK'; ld.size=110; ld.color=(.68,.65,.59)
    bounce=bpy.data.objects.new('Dimorphos_Bounce',ld); C.link(bounce,'Lights')
    bounce.location=(0,-85,20)
    CAM.point_at(bounce,pos)
    return d


def focus(cam,target,fstop=7.1):
    cam.data.dof.use_dof=True
    cam.data.dof.focus_object=target
    cam.data.dof.aperture_fstop=fstop
    cam.data.dof.aperture_blades=7


def hero(shot,t0):
    n=SHOTS[shot]; sc=base(n,48)
    dimorphos(rocks=4200)
    d=spacecraft((0,-185,8))
    cam,tgt=CAM.camera_rig('Cam_'+shot,lens=48,clip_start=.03)
    fps=C.scene_fps(sc)
    def path(f):
        t=t0+(f-1)/fps
        return ((24-.8*t,-242+1.2*t,28-.8*t),(0,-185+t,10))
    keycam(cam,tgt,n,path)
    for f in (1,n):
        t=t0+(f-1)/fps
        d['root'].location=(0,-185+t,8); d['root'].keyframe_insert('location',frame=f)
    A.set_interpolation(d['root'],'LINEAR',extrapolate='LINEAR')
    focus(cam,d['root'],8)
    print(f'EVENT {shot} reveal: 1:0.4')
    return finish(sc,cam,n)


def shot_v1():
    return hero('v1',0.)


def shot_v2():
    n=SHOTS['v2']; sc=base(n,48,ex=1.1)
    dimorphos(rocks=3000)
    d=spacecraft((0,-150,8))
    cam,tgt=CAM.camera_rig('Cam_v2',lens=58,clip_start=.02)
    def path(f):
        t=(f-1)/(n-1)
        return ((-4.5+3.0*t,-144+1*t,11.68-.6*t),(-.4+.6*t,-150,8.18))
    keycam(cam,tgt,n,path)
    focus(cam,d['root'],11)
    print('EVENT v2 spacecraft: 1:0.7')
    return finish(sc,cam,n)


def contact_point(a):
    return a['surface_point']((0,-1,.045))+Vector((0,-.2,.15))


def hide_after(root,frame,n):
    for ob in [root]+list(root.children_recursive):
        ob.hide_render=False; ob.keyframe_insert('hide_render',frame=frame-1)
        ob.hide_render=True; ob.keyframe_insert('hide_render',frame=frame)
        ob.keyframe_insert('hide_render',frame=n)


def shot_v3():
    n=SHOTS['v3']; sc=base(n,40,ex=1.1)
    a=dimorphos(rocks=4200); p=contact_point(a)
    d=spacecraft(p+Vector((0,-75,0)))
    for f,pos in [(1,p+Vector((0,-75,0))),(19,p+Vector((0,-1.2,0))),(20,p)]:
        d['root'].location=pos; d['root'].keyframe_insert('location',frame=f)
    A.set_interpolation(d['root'],'LINEAR'); hide_after(d['root'],21,n)
    ej=IMP.build_ejecta('Impact',p,(0,-1,.08),a['rock_meshes'],count=14000,seed=SY.SEED,
                        speed=(1,23),size=(.035,1.4))
    IMP.key_age(ej,[(1,-.01),(19,-.01),(20,0),(n,8.)])
    cam,tgt=CAM.camera_rig('Cam_v3',lens=40,clip_start=.05)
    cam.constraints[0].up_axis='UP_X'
    keycam(cam,tgt,n,lambda f: ((-215-25*(f-1)/(n-1),-270-30*(f-1)/(n-1),140),
                              (0,-50-15*(f-1)/(n-1),8)))
    print('EVENT v3 impact: 20:1.0')
    return finish(sc,cam,n)


def shot_v4():
    n=SHOTS['v4']; sc=base(n,40,ex=1.1)
    a=dimorphos(rocks=4200); p=contact_point(a)
    ej=IMP.build_ejecta('Ejecta',p,(0,-1,.08),a['rock_meshes'],count=14000,seed=SY.SEED,
                        speed=(1,23),size=(.035,1.4))
    IMP.key_age(ej,[(1,8.),(n,18.)])
    cam,tgt=CAM.camera_rig('Cam_v4',lens=32)
    cam.constraints[0].up_axis='UP_X'
    keycam(cam,tgt,n,lambda f: ((-380-35*(f-1)/(n-1),-120,180),
                              (0,-105-10*(f-1)/(n-1),15)))
    # Вектор отдачи накладывается в VSE: указатель не заслоняется поверхностью.
    print('EVENT v4 recoil: 130:0.55')
    return finish(sc,cam,n)


def shot_v5():
    n=SHOTS['v5']; sc=base(n,32,ex=1.1)
    AST.build_asteroid('Didymos',radius=SY.DIDYMOS_R,axes=(1.05,1.,.87),seed=6055,
                       detail='mid',boulder_count=510,texture=STONE_TEXTURE)
    a=dimorphos(detail='mid',rocks=420)
    cam,tgt=CAM.camera_rig('Cam_v5',lens=48,clip_start=.1)
    keycam(cam,tgt,n,lambda f: ((2400-260*(f-1)/(n-1),-4900,4100+180*(f-1)/(n-1)),(0,0,0)))
    for name,r,col,width in [('Before',SY.ORBIT_BEFORE,(.25,.47,.73),.8),
                             ('After',SY.ORBIT_AFTER,(1,.55,.18),1.1)]:
        pts=[(r*math.cos(i*math.tau/240),r*math.sin(i*math.tau/240),0) for i in range(241)]
        line=PLN.build_path_line(name,pts,cam=cam,px=width,color=col,strength=.9,head=1,trail=1,floor=.65)
        if name=='After':
            PLN.key_head(line,0.,1.,45,150)
    periods=ORB.video_periods({'before':SY.P_BEFORE_S,'after':SY.P_AFTER_S},ref='after',ref_seconds=8.)
    fps=C.scene_fps(sc)
    for f in sorted(set(range(1,n+1,3))|{n}):
        phase=-.5+(f-1)/fps/periods['after']*math.tau
        a['root'].location=(SY.ORBIT_AFTER*math.cos(phase),SY.ORBIT_AFTER*math.sin(phase),0)
        a['root'].keyframe_insert('location',frame=f)
    A.set_interpolation(a['root'],'LINEAR')
    print('EVENT v5 period: 121:0.75')
    return finish(sc,cam,n)


def shot_v6():
    return hero('v6',-8.)


BUILDERS={'v1':shot_v1,'v2':shot_v2,'v3':shot_v3,'v4':shot_v4,'v5':shot_v5,'v6':shot_v6}
if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    if 'timing' in args:
        import time
        from spacekit import render as R
        S.OPT['pct']=100
        sc,n=BUILDERS[args[0]]()
        sc.render.use_persistent_data=True
        folder=os.path.join(OUT,'timing'); os.makedirs(folder,exist_ok=True)
        for f in [n//2,n//2+1,n//2+2]:
            tic=time.perf_counter()
            R.render_still(os.path.join(folder,f'{args[0]}_{f:04d}.png'),frame=f)
            print(f'TIMING {args[0]} frame={f} seconds={time.perf_counter()-tic:.3f}',flush=True)
    else:
        S.run(BUILDERS,out_dir=OUT,render_end={'v6':480})
