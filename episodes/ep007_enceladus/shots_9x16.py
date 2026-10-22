"""Эп007 — Энцелад: 59.5с, 3570 кадров, EN.
Вопрос → ледяная луна → трещины → льдинка → состав → предел знания → шлейф.
Км; локальный рельеф — реконструкция, макро — увеличение, время потока условное.
CLI: -- vN preview 1,100,... pct=50 | draft [pct=50 samples=8 step=4 start=1] | timing | final.
"""
import math
import os
import shutil
import sys
import time
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.abspath(os.path.join(HERE,'..','..')))
sys.path.insert(0,HERE)
import bpy
from mathutils import Vector
from spacekit import anim as A, camera as CAM, core as C, lighting as LT, shot as S, sky as SKY
from spacekit import render as R
from spacekit.bodies import enceladus as EN, gas_giant as GG, rings as RG
from spacekit.fx import plumes as PL
import system as SY
EP=os.path.basename(HERE)
OUT=os.path.join(C.OUT,EP,'9x16')
MAP=os.path.join(HERE,'enc4k.jpg')
ICE_DETAIL=os.path.join(HERE,'icefine.jpg')
if not os.path.isfile(MAP):
    raise FileNotFoundError('Нужна карта Cassini: '+MAP)
# OptiX не может писать стандартный AppData-кэш из sandbox; используем рабочий out/.
os.environ.setdefault('OPTIX_CACHE_PATH',os.path.join(C.OUT,'oc'))
os.makedirs(os.environ['OPTIX_CACHE_PATH'],exist_ok=True)
S.OPT.update(fmt='9x16',fps=60)
SHOTS={'v1':300,'v2':480,'v3':540,'v4':420,'v5':600,'v6':600,'v7':631}
SUN_LOCAL=Vector((-.83,.52,.20)).normalized()
SUN_GLOBAL=Vector((-.65,-.7,.3)).normalized()
GAL=SKY.gal_for_view((-3.5,9,.8),tilt_deg=-22,l_center_deg=90)
GRAIN_RADIUS=.012
_grain_y=-9.0
_grain_x=float(EN.stripe_x(_grain_y,-17.5))
GRAIN_POS=Vector((_grain_x,_grain_y,float(EN.height(_grain_x,_grain_y))+5.5))
MICRO_SCALE=.018
MICRO_POS=Vector((.0,-.10,.18))


def keys(cam,tgt,n,fn,step=4):
    for f in sorted(set(range(1,n+1,step))|{n}):
        loc,look=fn(f)
        cam.location=loc; cam.keyframe_insert('location',frame=f)
        tgt.location=look; tgt.keyframe_insert('location',frame=f)
    A.set_interpolation(cam,'LINEAR',extrapolate='LINEAR'); A.set_interpolation(tgt,'LINEAR',extrapolate='LINEAR')
    bpy.context.scene.frame_set(1)


def base(n,samples=32,ex=.8):
    sc=S.base_scene(n,samples=min(samples,48),exposure=ex,adaptive=.035,bloom_strength=.12,
                    look='AgX - Medium High Contrast',comp=dict(bloom_threshold=1.5,bloom_size=.35,fog_strength=.015,dispersion=0,vignette=.08))
    sc.render.use_persistent_data=True
    sc.cycles.volume_step_rate=1.5
    return sc


def light(direction=SUN_LOCAL,strength=4.2,fill=.11,saturn_dir=(-.8,-.6,.01)):
    lamp,disk=LT.add_distant_sun('Sun',direction,strength=strength,angle_deg=.056,
                                 star_dist=3e6,star_radius=50,star_strength=5)
    # Слабый прокси света Сатурна: большой угловой размер, мягкие тени.
    ld=bpy.data.lights.new('Saturnshine','SUN'); ld.energy=fill; ld.angle=math.radians(25)
    ob=bpy.data.objects.new('Saturnshine',ld); C.link(ob,'Lights')
    CAM.point_at(ob,-Vector(saturn_dir))
    disk.hide_render=True
    return disk


def finish(sc,cam,n,disk=None,global_view=False,studio_view=False,grain_environment=False):
    # Постоянная ориентация неба v1/v7 сохраняет шов петли.
    if studio_view:
        sc.world.use_nodes=True; N=sc.world.node_tree.nodes; L=sc.world.node_tree.links; N.clear()
        out=N.new('ShaderNodeOutputWorld'); env=N.new('ShaderNodeBackground'); bg=N.new('ShaderNodeBackground')
        env.inputs['Color'].default_value=(.35,.45,.55,1); env.inputs['Strength'].default_value=.35
        bg.inputs['Color'].default_value=(.002,.004,.008,1); bg.inputs['Strength'].default_value=.2
        lp=N.new('ShaderNodeLightPath'); mix=N.new('ShaderNodeMixShader')
        L.new(lp.outputs['Is Camera Ray'],mix.inputs[0]); L.new(env.outputs[0],mix.inputs[1]); L.new(bg.outputs[0],mix.inputs[2])
        L.new(mix.outputs[0],out.inputs[0])
    else:
        st=SKY.build_sky(sc,cam,sc.view_settings.exposure,gal=GAL,
                         mw_strength=.14,star_brightness=.65,mag_limit=10,n_stars=300000,
                         star_px=.60,contrast=1.05,band_frac=.75)
        if global_view: st.scale=(100,100,100)
        if grain_environment: reflection_environment(sc)
    R.setup_volume_denoise(sc,'far')
    if not studio_view: R.setup_star_layer(sc,st,samples=16)
    sc.cycles.volume_bounces=1
    return sc,n


def local_sources():
    result=[]
    for y in [-30,-24,-15,-9,2,9,20,27]:
        x=float(EN.stripe_x(y,-17.5)); result.append((x,y,float(EN.height(x,y))+.08))
    return result


def hook_pose(f):
    t=(f-1)/C.scene_fps()
    y=-22+.5*t; x=float(EN.stripe_x(y,-17.5))+3.5
    ly=y+9; lx=float(EN.stripe_x(ly,-17.5))
    return (x,y,float(EN.height(x,y))+.65),(lx,ly,float(EN.height(lx,ly))+.45)


def hero(shot,offset=0):
    n=SHOTS[shot]; sc=base(n,24,ex=.65)
    EN.build_terrain(resolution=620,texture=MAP,detail_texture=ICE_DETAIL)
    PL.build_plumes('OceanSpray',local_sources(),height=40,width=6,count=9000,
                    seed=SY.SEED,frame_end=n,time0=offset/C.scene_fps(sc),time1=(offset+n-1)/C.scene_fps(sc),density=.35)
    cam,tgt=CAM.camera_rig('Cam_'+shot,lens=42,clip_start=.02,clip_end=1e7)
    def pose(f):
        loc,look=hook_pose(f+offset)
        if shot=='v7':
            # Ранний подъём/поворот, линейный хвост90 кадров до точного стыка.
            q=max(0,1-(f-1)/(n-91)); q=q*q*(3-2*q)
            loc=Vector(loc)+Vector((9,-19,20))*q
            look=Vector(look)+Vector((0,0,11))*q
        return loc,look
    keys(cam,tgt,n,pose)
    disk=light()
    print(f'EVENT {shot} plume: 1:0.45',flush=True)
    return finish(sc,cam,n,disk)


def shot_v1():
    return hero('v1')


def shot_v2():
    n=SHOTS['v2']; sc=base(n,24,ex=.65)
    EN.build_globe(texture=MAP)
    cam,tgt=CAM.camera_rig('Cam_v2',lens=38,clip_start=.2,clip_end=1e7)
    keys(cam,tgt,n,lambda f: ((680-100*(f-1)/(n-1),-1450+60*(f-1)/(n-1),540),(0,0,160)))
    view=Vector((-680,1450,-450)).normalized()
    up=(Vector((0,0,1))-view*view.z).normalized(); right=view.cross(up)
    satdir=(view+up*.25+right*.025).normalized()
    satpos=satdir*SY.SATURN_DIST_KM
    axis=(Vector((0,0,1))-satdir*satdir.z).normalized()
    # Солнце в 3° от плоскости колец: узкая физическая тень вместо чёрного полудиска.
    in_plane=SUN_GLOBAL-axis*SUN_GLOBAL.dot(axis)
    sun=in_plane.normalized()*math.cos(math.radians(3))+axis*math.sin(math.radians(3))
    rot=axis.to_track_quat('Z','Y').to_euler()
    g=GG.build_gas_giant(sc,'saturn',radius=SY.SATURN_R_KM,location=satpos,
                         rotation_euler=rot,sun_dir=sun,sun_strength=4.2,
                         detail='close',seed=SY.SEED,frame_end=n,haze=True)
    RG.build_rings(sc,'saturn',parent=g['root'],unit_km=1,sun_dir=sun,detail='close')
    disk=light(sun,saturn_dir=satdir)
    print('EVENT v2 moon: 1:0.6',flush=True)
    return finish(sc,cam,n,disk,global_view=True)


def shot_v3():
    n=SHOTS['v3']; sc=base(n,32,ex=.65)
    EN.build_terrain(extent=(90,100),resolution=760,texture=MAP,detail_texture=ICE_DETAIL)
    PL.build_plumes('CloseJets',local_sources()[1:7],height=38,width=5.4,count=9000,seed=SY.SEED,
                    frame_end=n,time0=0,time1=9,density=.35)
    grain=EN.ice_grain(radius=GRAIN_RADIUS,location=GRAIN_POS,seed=SY.SEED)
    grain.rotation_euler=(.2,.1,-.1)
    cam,tgt=CAM.camera_rig('Cam_v3',lens=60,clip_start=.00002,clip_end=1e7)
    def pose(f):
        t=(f-1)/(n-1); y=-34+8*t
        x=float(EN.stripe_x(y,-17.5))+9
        lx=float(EN.stripe_x(y+20,-17.5))
        loc=Vector((x,y,float(EN.height(x,y)) +2.2))
        look=Vector((lx,y+20,float(EN.height(lx,y+20))+5.5))
        q=smooth((t-.73)/.27)
        if q:
            end=Vector((.55,-6.8,1.6))*GRAIN_RADIUS
            a=loc-GRAIN_POS; direction=(a.normalized()*(1-q)+end.normalized()*q).normalized()
            dist=math.exp(math.log(a.length)*(1-q)+math.log(end.length)*q)
            loc=GRAIN_POS+direction*dist
            look=look.lerp(GRAIN_POS+Vector((0,0,.1))*GRAIN_RADIUS,min(1,q*4))
        return loc,look
    keys(cam,tgt,n,pose,step=2)
    disk=light(SUN_LOCAL,fill=.12)
    ice_fill(GRAIN_POS,GRAIN_RADIUS)
    print('EVENT v3 fracture: 1:0.5',flush=True)
    print('EVENT v3 zoom_grain: 420:0.7',flush=True)
    print('EVENT v3 studio_handoff: 490:0.15, 530:0.15',flush=True)
    result=finish(sc,cam,n,disk,grain_environment=True)
    fade_background(sc,grain,490,530)
    return result


def studio(sc):
    # Условное освещение увеличенной иллюстрации, не наблюдение льдинки в космосе.
    light(SUN_LOCAL,strength=4.2,fill=.12)
    ice_fill()


def ice_fill(origin=(0,0,0),scale=1):
    origin=Vector(origin)
    ld=bpy.data.lights.new('IceBounce','AREA'); ld.energy=95*scale*scale; ld.shape='DISK'; ld.size=3*scale
    ob=bpy.data.objects.new('IceBounce',ld); C.link(ob,'Lights'); ob.location=origin+Vector((3,1,2))*scale
    CAM.point_at(ob,origin)


def fade_value(N,frames,visible=True):
    node=N.new('ShaderNodeValue')
    for f,v in [(1,1),(frames[0],1),(frames[1],0)]:
        node.outputs[0].default_value=v; node.outputs[0].keyframe_insert('default_value',frame=f)
    return node.outputs[0]


def fade_background(sc,keep,start,end):
    """Конец зума переходит в явно иллюстративную макросцену без скачка фона."""
    # GN-инстансы держат материалы в SetMaterial, а не в слотах исходного меша.
    mats={m for m in bpy.data.materials if m.use_nodes and m not in keep.data.materials[:]}
    for mat in mats:
        N,L=mat.node_tree.nodes,mat.node_tree.links
        out=next((n for n in N if n.type=='OUTPUT_MATERIAL'),None)
        if not out: continue
        span=(450,480) if mat.name=='CloseJets_IceMat' else (start,end)
        val=fade_value(N,span)
        if out.inputs['Surface'].is_linked:
            src=out.inputs['Surface'].links[0].from_socket
            tr=N.new('ShaderNodeBsdfTransparent'); mix=N.new('ShaderNodeMixShader')
            L.new(val,mix.inputs[0]); L.new(tr.outputs[0],mix.inputs[1]); L.new(src,mix.inputs[2])
            L.new(mix.outputs[0],out.inputs['Surface'])
        for node in list(N):
            if node.type=='VOLUME_SCATTER' and node.inputs['Density'].is_linked:
                src=node.inputs['Density'].links[0].from_socket
                L.new(C.math_node(N,L,'MULTIPLY',src,val),node.inputs['Density'])
        A.set_interpolation(mat.node_tree,'LINEAR')


def reflection_environment(sc):
    N,L=sc.world.node_tree.nodes,sc.world.node_tree.links
    out=next(n for n in N if n.type=='OUTPUT_WORLD'); old=out.inputs['Surface'].links[0].from_socket
    # Отражения макрольдинки совпадают с v4; камера продолжает видеть исходное звёздное поле.
    env=N.new('ShaderNodeBackground'); env.inputs[0].default_value=(.35,.45,.55,1); env.inputs[1].default_value=.35
    black=N.new('ShaderNodeBackground'); black.inputs[0].default_value=(.002,.004,.008,1); black.inputs[1].default_value=.2
    fade=fade_value(N,(490,530)); inverse=C.math_node(N,L,'SUBTRACT',1,fade)
    bg=N.new('ShaderNodeMixShader'); L.new(inverse,bg.inputs[0]); L.new(old,bg.inputs[1]); L.new(black.outputs[0],bg.inputs[2])
    lp=N.new('ShaderNodeLightPath'); refl=C.math_node(N,L,'MAXIMUM',lp.outputs['Is Glossy Ray'],lp.outputs['Is Transmission Ray'])
    mix=N.new('ShaderNodeMixShader'); L.new(refl,mix.inputs[0]); L.new(bg.outputs[0],mix.inputs[1]); L.new(env.outputs[0],mix.inputs[2])
    L.new(mix.outputs[0],out.inputs['Surface']); A.set_interpolation(sc.world.node_tree,'LINEAR')


def shot_v4():
    n=SHOTS['v4']; sc=base(n,32,ex=.65)
    grain=EN.ice_grain(radius=1,seed=SY.SEED)
    for f,rot in [(1,(.2,.1,-.1)),(270,(.27,.22,.08)),(n,(.27,.22,.08))]:
        grain.rotation_euler=rot; grain.keyframe_insert('rotation_euler',frame=f)
    A.set_interpolation(grain,'LINEAR')
    cam,tgt=CAM.camera_rig('Cam_v4',lens=60,clip_start=.01,clip_end=1e7)
    def pose(f):
        t=(f-1)/(n-1); q=smooth((t-.60)/.40)
        loc=Vector((.55-.15*min(t/.60,1),-6.8+.3*min(t/.60,1),1.6))
        look=Vector((0,0,.1))
        endloc=MICRO_POS+Vector((0,-7.8,1.4))*MICRO_SCALE
        endlook=MICRO_POS+Vector((0,0,.6))*MICRO_SCALE
        if q:
            a=loc-endlook; b=endloc-endlook
            direction=(a.normalized()*(1-q)+b.normalized()*q).normalized()
            loc=endlook+direction*math.exp(math.log(a.length)*(1-q)+math.log(b.length)*q)
            look=look.lerp(endlook,q)
        return loc,look
    keys(cam,tgt,n,pose,step=2)
    fade_ice(grain,330,395)
    micro=C.empty('MicroWorld',coll='Diagram',loc=MICRO_POS); micro.scale=(MICRO_SCALE,)*3
    water=chemistry(n,water_only=True)['water']; water.parent=micro
    for f,s in [(1,.00001),(310,.00001),(350,1),(n,1)]:
        water.scale=(s,)*3; water.keyframe_insert('scale',frame=f)
    for f in [1,n]:
        water.rotation_euler.z=-.12; water.keyframe_insert('rotation_euler',frame=f)
    A.set_interpolation(water,'LINEAR')
    studio(sc)
    print('EVENT v4 grain: 1:0.7',flush=True)
    print('EVENT v4 zoom_chemistry: 330:0.7',flush=True)
    # Длительное исчезновение оболочки: контроль PNG учитывает весь интервал, не только конец.
    print('EVENT v4 ice_dissolve: '+', '.join(f'{f}:0.15' for f in [*range(330,395,6),395]),flush=True)
    print('EVENT v4 ice_handoff: 395:0.15',flush=True)
    return finish(sc,cam,n,studio_view=True)


def smooth(t):
    t=min(1,max(0,t)); return t*t*t*(t*(t*6-15)+10)


def fade_ice(ob,start,end):
    mat=ob.data.materials[0]; N,L=mat.node_tree.nodes,mat.node_tree.links
    out=next(n for n in N if n.type=='OUTPUT_MATERIAL')
    src=out.inputs['Surface'].links[0].from_socket
    tr=N.new('ShaderNodeBsdfTransparent'); mix=N.new('ShaderNodeMixShader')
    L.new(tr.outputs[0],mix.inputs[1]); L.new(src,mix.inputs[2]); L.new(mix.outputs[0],out.inputs['Surface'])
    for f,v in [(1,1),(start,1),(end,0),(SHOTS['v4'],0)]:
        mix.inputs[0].default_value=v; mix.inputs[0].keyframe_insert('default_value',frame=f)
    for node in N:
        if node.type=='VOLUME_SCATTER':
            for f,v in [(1,.035),(start,.035),(end,0)]:
                node.inputs['Density'].default_value=v; node.inputs['Density'].keyframe_insert('default_value',frame=f)
    A.set_interpolation(mat.node_tree,'LINEAR')


def diagram_mat(name,color):
    mat,N,L,out=C.new_material(name)
    bs=N.new('ShaderNodeBsdfPrincipled'); bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=.3; L.new(bs.outputs[0],out.inputs['Surface'])
    return mat


def diagram_ball(name,pos,r,mat,parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=r,location=pos)
    ob=bpy.context.object; ob.name=name; C.link(ob,'Diagram'); ob.parent=parent
    ob.data.materials.append(mat)
    for p in ob.data.polygons: p.use_smooth=True
    return ob


def diagram_bond(name,a,b,mat,parent):
    a,b=Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.022,depth=(b-a).length,location=(a+b)*.5)
    ob=bpy.context.object; ob.name=name; C.link(ob,'Diagram'); ob.parent=parent
    ob.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler(); ob.data.materials.append(mat)


def diagram_group(name,center,start,n):
    root=C.empty(name,coll='Diagram',loc=center)
    for f,s in [(1,.001 if start else 1),(max(2,start),.001 if start else 1),(max(3,start+18),1),(n,1)]:
        root.scale=(s,s,s); root.keyframe_insert('scale',frame=f)
    for f,r in [(1,-.12),(n,.15)]:
        root.rotation_euler.z=r; root.keyframe_insert('rotation_euler',frame=f)
    A.set_interpolation(root,'LINEAR')
    return root


def chemistry(n,water_only=False):
    oxygen=diagram_mat('Oxygen',(.52,.12,.075)); hydrogen=diagram_mat('Hydrogen',(.8,.9,1))
    phosphorus=diagram_mat('Phosphorus',(.85,.5,.1)); ion=diagram_mat('SaltIon',(.2,.43,.7))
    water=diagram_group('Water',(-.58,0,1.55),0,n)
    diagram_ball('O',(0,0,0),.145,oxygen,water)
    for j,p in enumerate([(-.19,0,.15),(.19,0,.15)]):
        diagram_ball('H'+str(j),p,.085,hydrogen,water); diagram_bond('OH'+str(j),(0,0,0),p,hydrogen,water)
    if water_only: return dict(water=water)
    salt=diagram_group('Salt',(-.58,0,1.0),95,n)
    diagram_ball('IonA',(-.15,0,0),.12,ion,salt); diagram_ball('IonB',(.15,0,0),.145,hydrogen,salt)
    ph=diagram_group('Phosphate',(-.58,0,.43),345,n)
    diagram_ball('P',(0,0,0),.11,phosphorus,ph)
    for j,p in enumerate([(.16,.16,.16),(.16,-.16,-.16),(-.16,.16,-.16),(-.16,-.16,.16)]):
        diagram_ball('PO'+str(j),p,.092,oxygen,ph); diagram_bond('POBond'+str(j),(0,0,0),p,hydrogen,ph)
    return dict(water=water,salt=salt,phosphate=ph)


def shot_v5():
    n=SHOTS['v5']; sc=base(n,24,ex=.65)
    cam,tgt=CAM.camera_rig('Cam_v5',lens=60,clip_start=.01,clip_end=1e7)
    keys(cam,tgt,n,lambda f: ((0,-7.8,1.4),(0,0,.6)))
    studio(sc); chemistry(n)
    # Состав — объяснительная схема, не изображение измеренной структуры зерна.
    print('EVENT v5 salts: 109:0.6',flush=True)
    print('EVENT v5 phosphates: 361:0.75',flush=True)
    return finish(sc,cam,n,studio_view=True)


def shot_v6():
    n=SHOTS['v6']; sc=base(n,16,ex=.6)
    EN.build_globe(texture=MAP)
    sources=[(x,y,-math.sqrt(SY.R_KM**2-x*x-y*y)) for x,y in [(-15,-5),(15,5)]]
    PL.build_plumes('GlobalSpray',sources,height=110,width=18,count=1600,seed=SY.SEED,
                    frame_end=n,time0=0,time1=10,density=.07,axis=(0,0,-1))
    cam,tgt=CAM.camera_rig('Cam_v6',lens=55,clip_start=.1,clip_end=1e7)
    keys(cam,tgt,n,lambda f: ((350+80*(f-1)/(n-1),-1400,-600+110*(f-1)/(n-1)),(0,0,-190)))
    disk=light(Vector((-.6,.8,-.02)).normalized(),fill=.10)
    print('EVENT v6 unknown: 1:0.5',flush=True)
    return finish(sc,cam,n,disk)


def shot_v7():
    return hero('v7',offset=-630)


BUILDERS={'v1':shot_v1,'v2':shot_v2,'v3':shot_v3,'v4':shot_v4,'v5':shot_v5,'v6':shot_v6,'v7':shot_v7}


def draft(argv):
    step=next((int(a[5:]) for a in argv if a.startswith('step=')),4)
    start=next((int(a[6:]) for a in argv if a.startswith('start=')),1)
    args=[a for a in argv if a!='draft' and not a.startswith(('step=','start='))]
    if not any(a.startswith('pct=') for a in args): args.append('pct=50')
    if not any(a.startswith('samples=') for a in args): args.append('samples=8')
    S.run(BUILDERS,out_dir=OUT,argv=args)
    shot=args[0]; n=SHOTS[shot] if shot!='v7' else 630
    d=os.path.join(OUT,'draft_r2',shot)
    R.render_sequence(d,start,n,step=step)
    for f in range(start,n+1,step):
        src=os.path.join(d,f'{f:04d}.png')
        for g in range(f+1,min(f+step,n+1)):
            dst=os.path.join(d,f'{g:04d}.png')
            if not os.path.exists(dst): shutil.copyfile(src,dst)


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    if 'draft' in args:
        if os.path.exists(os.path.join(OUT,'PAUSE_PREVIEW')):
            raise SystemExit('Превью приостановлено между шотами: PAUSE_PREVIEW')
        draft(args)
    elif 'timing' in args:
        S.OPT['pct']=100; sc,n=BUILDERS[args[0]]()
        d=os.path.join(OUT,'timing_r2'); os.makedirs(d,exist_ok=True)
        for f in [n//2,n//2+1,n//2+2]:
            tic=time.perf_counter(); R.render_still(os.path.join(d,f'{args[0]}_{f:04d}.png'),frame=f)
            print(f'TIMING {args[0]} {f}: {time.perf_counter()-tic:.3f}',flush=True)
    else:
        S.run(BUILDERS,out_dir=OUT,render_end={'v7':630})
