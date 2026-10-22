"""Энцелад: глобус по карте Cassini и локальный южнополярный рельеф.

Единица = 1 км. Локальные трещины — реконструкция по размерам Porco2006,
не DEM. +Z локального участка направлена наружу у южного полюса.
"""
import math
import os

import bpy
import numpy as np
from .. import core as C


RADIUS = 252.1
STRIPES = (-52.5, -17.5, 17.5, 52.5)


def _hash(x,y,seed):
    n=(np.asarray(x,dtype=np.int64)*374761393+np.asarray(y,dtype=np.int64)*668265263+seed*144269)&0xffffffff
    n=((n^(n>>13))*1274126177)&0xffffffff
    return (n^(n>>16))/4294967295.0


def noise(x,y,scale=1,seed=7):
    """Детерминированный непериодический value noise, общий для сетки и обломков."""
    x,y=np.asarray(x)/scale,np.asarray(y)/scale
    ix,iy=np.floor(x),np.floor(y); u,v=x-ix,y-iy
    u=u*u*u*(u*(u*6-15)+10); v=v*v*v*(v*(v*6-15)+10)
    a=_hash(ix,iy,seed)*(1-u)+_hash(ix+1,iy,seed)*u
    b=_hash(ix,iy+1,seed)*(1-u)+_hash(ix+1,iy+1,seed)*u
    return (a*(1-v)+b*v)*2-1


def stripe_x(y, offset):
    y=np.asarray(y)
    return offset+2.8*noise(y*0,y,27,17+int(offset+60))+.65*noise(y*0,y,5,33)+.10*noise(y*0,y,.7,41)


def height(x, y):
    """Высоты в км: непериодический раздробленный лёд и ступенчатые V-разломы."""
    x, y = np.asarray(x), np.asarray(y)
    z = -(x*x+y*y)/(2*RADIUS)
    z += .18*noise(x,y,35,7)+.055*noise(x,y,9,8)+.025*noise(x,y,1.5,9)
    z += .008*noise(x,y,.40,10)+.003*noise(x,y,.12,11)
    for off in STRIPES:
        d = x-stripe_x(y, off)
        width=1.0+.22*noise(y*0,y,3.7,71)
        u=np.abs(d)/(width*np.where(d<0,.8,1.2))
        raw=-(.38+.06*noise(y*0,y,4.1,73))*np.clip((1-u)/.75,0,1)
        # Неровные отвесы без равномерных изолиний и одинаковых террас.
        raw += .065*noise(x,y,.28,74)*np.clip(1-u,0,1)
        z += raw
        z -= .13*np.maximum(0,1-np.abs(d)/(.09+.025*noise(y*0,y,.8,75)))
        ridge=.10*np.maximum(0,1-np.abs(u-1.25)/.38)
        z += ridge*(.7+.3*noise(x,y,1.7,77))
    # Поперечные короткие разрывы, а не равномерная сетка волн.
    main=x-stripe_x(y,-17.5)
    for j,(yc,angle,length) in enumerate([(-52,.6,14),(-34,-.8,9),(-17,.45,12),(2,-.55,8),(19,.75,15),(42,-.4,11)]):
        dist=(y-yc)-angle*main-.16*noise(x,y,.8,90+j)
        z -= (.035+.02*(j%3))*np.maximum(0,1-np.abs(dist)/.10)*np.exp(-(main/length)**4)
    return z


def surface_height(x, y):
    """Раздробленный покров поверх крупных разломов; height сохраняет траекторию камеры."""
    x,y=np.asarray(x),np.asarray(y)
    wx=x+.24*noise(x,y,1.6,211); wy=y+.24*noise(x,y,1.9,212)
    # Как у астероида: абсолютная величина поля даёт изломы, а не мягкие бугорки.
    # Частоты не кратны друг другу; вытянутые складки пересекаются со сколами.
    a=noise(wx,wy*.72,.64,213)
    b=noise(wx*.81+wy*.36,-wx*.31+wy*.9,.19,214)
    c=noise(wx,wy,.061,215)
    relief=.072*(abs(a)-.28)+.028*(abs(b)-.27)+.008*(abs(c)-.26)
    relief+=.012*noise(wx,wy,.13,216)
    return height(x,y)+relief


def ice_material(name, texture=None, local=False,detail_texture=None):
    mat,N,L,out=C.new_material(name)
    tc=N.new('ShaderNodeTexCoord')
    if local:
        def tex(scale,detail=3,rough=.76):
            no=N.new('ShaderNodeTexNoise'); no.inputs['Scale'].default_value=scale
            no.inputs['Detail'].default_value=detail; no.inputs['Roughness'].default_value=rough
            L.new(tc.outputs['Object'],no.inputs['Vector'])
            return no
        coarse=tex(1.8,5)
        col=N.new('ShaderNodeValToRGB'); col.color_ramp.elements[0].position=.18
        col.color_ramp.elements[0].color=(.48,.54,.58,1)
        col.color_ramp.elements[1].position=.82; col.color_ramp.elements[1].color=(.88,.92,.94,1)
        L.new(coarse.outputs['Fac'],col.inputs[0])
        chip=tex(7.5,4,.82); grain=tex(48,3,.78); micro=tex(220,2,.75)
        # Общий height для единственного Bump: цепочка сильных нормалей давала клетчатый базис сетки.
        ridge=C.math_node(N,L,'ABSOLUTE',C.math_node(N,L,'SUBTRACT',chip.outputs['Fac'],.5))
        h=C.math_node(N,L,'MULTIPLY',ridge,.10)
        h=C.math_node(N,L,'ADD',h,C.math_node(N,L,'MULTIPLY',grain.outputs['Fac'],.010))
        h=C.math_node(N,L,'ADD',h,C.math_node(N,L,'MULTIPLY',micro.outputs['Fac'],.0015))
        warp=tex(.9,3)
        offset=N.new('ShaderNodeVectorMath'); offset.operation='SCALE'; offset.inputs['Scale'].default_value=.20
        L.new(warp.outputs['Color'],offset.inputs[0])
        add=N.new('ShaderNodeVectorMath'); add.operation='ADD'
        L.new(tc.outputs['Object'],add.inputs[0]); L.new(offset.outputs[0],add.inputs[1])
        cracks=N.new('ShaderNodeTexVoronoi'); cracks.feature='DISTANCE_TO_EDGE'
        cracks.inputs['Scale'].default_value=4.3; L.new(add.outputs[0],cracks.inputs['Vector'])
        edge=N.new('ShaderNodeMapRange'); edge.clamp=True
        edge.inputs['From Min'].default_value=.002; edge.inputs['From Max'].default_value=.022
        edge.inputs['To Min'].default_value=-.008; edge.inputs['To Max'].default_value=0
        L.new(cracks.outputs['Distance'],edge.inputs[0])
        # Прерывистые расколы, как у астероидного материала, без замкнутой «брусчатки».
        gate=N.new('ShaderNodeMapRange'); gate.clamp=True; gate.interpolation_type='SMOOTHSTEP'
        gate.inputs['From Min'].default_value=.43; gate.inputs['From Max'].default_value=.58
        L.new(chip.outputs['Fac'],gate.inputs[0])
        h=C.math_node(N,L,'ADD',h,C.math_node(N,L,'MULTIPLY',edge.outputs[0],gate.outputs[0]))
        color=col.outputs['Color']
        if detail_texture:
            # Высокочастотная фактура реального Cassini-снимка, не измеренная карта высот.
            vec=N.new('ShaderNodeVectorMath'); vec.operation='MULTIPLY_ADD'
            vec.inputs[1].default_value=(1/44.16,1/43.2,0); vec.inputs[2].default_value=(.37,.21,0)
            L.new(tc.outputs['Object'],vec.inputs[0])
            tex=N.new('ShaderNodeTexImage'); tex.image=bpy.data.images.load(detail_texture,check_existing=True)
            tex.image.colorspace_settings.name='Non-Color'; tex.extension='REPEAT'; L.new(vec.outputs[0],tex.inputs[0])
            contrast=N.new('ShaderNodeValToRGB'); contrast.color_ramp.elements[0].color=(.30,.34,.38,1)
            contrast.color_ramp.elements[1].color=(1.50,1.46,1.42,1)
            L.new(tex.outputs['Color'],contrast.inputs[0])
            mult=N.new('ShaderNodeMixRGB'); mult.blend_type='MULTIPLY'; mult.inputs[0].default_value=.90
            L.new(color,mult.inputs[1]); L.new(contrast.outputs[0],mult.inputs[2]); color=mult.outputs[0]
            h=C.math_node(N,L,'ADD',h,C.math_node(N,L,'MULTIPLY',tex.outputs['Color'],.010))
        bump=N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.72
        bump.inputs['Distance'].default_value=1
        L.new(h,bump.inputs['Height'])
        rough=N.new('ShaderNodeMapRange'); rough.inputs['To Min'].default_value=.78; rough.inputs['To Max'].default_value=.96
        L.new(grain.outputs['Fac'],rough.inputs[0])
        bs=N.new('ShaderNodeBsdfPrincipled'); bs.inputs['IOR'].default_value=1.31
        bs.inputs['Specular IOR Level'].default_value=.24
        L.new(color,bs.inputs['Base Color']); L.new(rough.outputs[0],bs.inputs['Roughness'])
        L.new(bump.outputs['Normal'],bs.inputs['Normal']); L.new(bs.outputs[0],out.inputs['Surface'])
        return mat
    noise=N.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=8 if local else 24
    noise.inputs['Detail'].default_value=5; noise.inputs['Roughness'].default_value=.7
    L.new(tc.outputs['Object' if local else 'Generated'],noise.inputs['Vector'])
    ramp=N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.2
    ramp.color_ramp.elements[0].color=(.45,.49,.52,1) if local else (.76,.78,.8,1)
    ramp.color_ramp.elements[1].position=.8
    ramp.color_ramp.elements[1].color=(.84,.88,.9,1) if local else (.83,.85,.87,1)
    L.new(noise.outputs['Fac'],ramp.inputs[0])
    col=ramp.outputs['Color']
    if texture and os.path.isfile(texture):
        tex=N.new('ShaderNodeTexImage'); tex.image=bpy.data.images.load(texture,check_existing=True)
        tex.interpolation='Linear'; L.new(tc.outputs['UV'],tex.inputs['Vector'])
        # Мозаика содержит фотометрические швы: не превращать их в геометрические горы.
        mix=N.new('ShaderNodeMixRGB'); mix.blend_type='MIX'; mix.inputs[0].default_value=.38 if local else .85
        L.new(col,mix.inputs[1]); L.new(tex.outputs['Color'],mix.inputs[2]); col=mix.outputs[0]
    fine=N.new('ShaderNodeTexNoise'); fine.inputs['Scale'].default_value=105 if local else 180
    fine.inputs['Detail'].default_value=3
    L.new(tc.outputs['Object' if local else 'Generated'],fine.inputs['Vector'])
    bump=N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.25
    bump.inputs['Distance'].default_value=.004 if local else .045
    L.new(fine.outputs['Fac'],bump.inputs['Height'])
    bs=N.new('ShaderNodeBsdfPrincipled')
    L.new(col,bs.inputs['Base Color']); L.new(bump.outputs['Normal'],bs.inputs['Normal'])
    bs.inputs['Roughness'].default_value=.72
    bs.inputs['Specular IOR Level'].default_value=.26
    L.new(bs.outputs[0],out.inputs['Surface'])
    return mat


def build_globe(name='Enceladus', radius=RADIUS, texture=None, location=(0,0,0), parent=None, detail='close'):
    seg=256 if detail=='close' else 128
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg,ring_count=seg//2,radius=radius,location=location)
    ob=bpy.context.object; ob.name=name; C.link(ob,'Enceladus')
    if parent: ob.parent=parent
    for p in ob.data.polygons: p.use_smooth=True
    ob.data.materials.append(ice_material(name+'_Ice',texture=texture))
    return dict(root=ob,body=ob,radius=radius)


def build_terrain(name='SouthPole', extent=(100,100), resolution=420, center=(0,0), parent=None,texture=None, rubble=True,detail_texture=None):
    """Кусок южного полюса. Центр и extent в километрах, без фальшивого свечения трещин."""
    # У камеры — сетка 10–20 м. За пределами пролёта плотность быстро уменьшается.
    hi=max(240,int(resolution*.65)); lo=max(80,int(resolution*.18))
    us=np.concatenate((np.linspace(-extent[0]+17.5,-12,lo,endpoint=False),
        np.linspace(-12,-4,200,endpoint=False),np.linspace(-4,4,max(hi,640),endpoint=False),
        np.linspace(4,12,500,endpoint=False),np.linspace(12,24,180,endpoint=False),np.linspace(24,extent[0]+17.5,lo)))
    ys=np.concatenate((np.linspace(center[1]-extent[1],-55,240,endpoint=False),
        np.linspace(-55,-30,350,endpoint=False),np.linspace(-30,-14,1000,endpoint=False),
        np.linspace(-14,25,650,endpoint=False),np.linspace(25,center[1]+extent[1],340)))
    u,y=np.meshgrid(us,ys)
    # Нерегулярные вершины исключают видимую прямоугольную структуру полигонов.
    dx=np.gradient(us)[None,:]; dy=np.gradient(ys)[:,None]
    rng=np.random.default_rng(7103)
    u+=rng.uniform(-.25,.25,u.shape)*dx; y+=rng.uniform(-.25,.25,y.shape)*dy
    x=stripe_x(y,-17.5)+u; z=surface_height(x,y)
    verts=np.stack((x,y,z),axis=-1).reshape(-1,3).astype(np.float32)
    nx,ny=len(us),len(ys)
    a=np.arange((ny-1)*nx).reshape(ny-1,nx)[:,:-1].ravel()
    faces=np.stack((a,a+1,a+nx+1,a+nx),axis=-1).astype(np.int32)
    me=bpy.data.meshes.new(name+'_Mesh')
    me.vertices.add(len(verts)); me.vertices.foreach_set('co',verts.ravel())
    me.loops.add(faces.size); me.loops.foreach_set('vertex_index',faces.ravel())
    me.polygons.add(len(faces)); me.polygons.foreach_set('loop_start',np.arange(len(faces),dtype=np.int32)*4)
    me.polygons.foreach_set('loop_total',np.full(len(faces),4,dtype=np.int32)); me.update()
    if texture:
        # Сферическая проекция южной полярной области фотомозаики; не DEM.
        u=(np.arctan2(y,x)/(2*np.pi)+.5)%1
        v=np.arcsin(np.clip(np.sqrt(x*x+y*y)/RADIUS,0,1))/np.pi
        uv=np.stack((u,v),axis=-1).reshape(-1,2)
        ids=np.empty(len(me.loops),dtype=np.int32); me.loops.foreach_get('vertex_index',ids)
        layer=me.uv_layers.new(name='Cassini'); layer.data.foreach_set('uv',uv[ids].ravel())
    ob=bpy.data.objects.new(name,me); C.link(ob,'Enceladus')
    if parent: ob.parent=parent
    me.polygons.foreach_set('use_smooth',np.ones(len(faces),dtype=bool))
    me.materials.append(ice_material(name+'_Ice',local=True,texture=texture,detail_texture=detail_texture))
    if rubble: build_rubble(name+'_Rubble',extent=extent,seed=707,count=12000)
    return dict(root=ob,body=ob,surface=lambda x,y:(x,y,float(surface_height(x,y))))


def build_rubble(name,extent=(100,100),seed=707,count=35000):
    """Угловатые ледяные обломки и осыпи 10–80 м; один инстансированный меш."""
    rng=np.random.default_rng(seed)
    y=rng.uniform(-extent[1],extent[1],count)
    d=rng.choice([-1,1],count)*(rng.power(.65,count)*3.2+.1)
    x=stripe_x(y,-17.5)+d
    # Группы у уступов и отдельные обломки на более широком поле.
    k=count//4; x[:k]=rng.uniform(-45,40,k); y[:k]=rng.uniform(-80,65,k)
    scales=rng.lognormal(np.log(.014),.48,(count,3)).clip(.003,.040)
    pos=np.stack((x,y,surface_height(x,y)-scales[:,2]*.15),axis=-1).astype(np.float32)
    me=bpy.data.meshes.new(name+'_Pts'); me.vertices.add(count); me.vertices.foreach_set('co',pos.ravel())
    for nm,arr in [('scale',scales),('rot',rng.uniform(-math.pi,math.pi,(count,3)))]:
        a=me.attributes.new(nm,'FLOAT_VECTOR','POINT'); a.data.foreach_set('vector',arr.astype(np.float32).ravel())
    ob=bpy.data.objects.new(name,me); C.link(ob,'Enceladus')
    ng=bpy.data.node_groups.new(name+'_GN','GeometryNodeTree')
    ng.interface.new_socket('Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    N,L=ng.nodes,ng.links; gi=N.new('NodeGroupInput'); go=N.new('NodeGroupOutput')
    ico=N.new('GeometryNodeMeshIcoSphere'); ico.inputs['Radius'].default_value=1; ico.inputs['Subdivisions'].default_value=2
    posnode=N.new('GeometryNodeInputPosition'); deform=N.new('ShaderNodeTexNoise')
    deform.inputs['Scale'].default_value=2.6; deform.inputs['Detail'].default_value=2
    L.new(posnode.outputs[0],deform.inputs['Vector'])
    size=C.math_node(N,L,'MULTIPLY',C.math_node(N,L,'SUBTRACT',deform.outputs['Fac'],.5),.50)
    offset=N.new('ShaderNodeVectorMath'); offset.operation='SCALE'
    L.new(posnode.outputs[0],offset.inputs[0]); L.new(size,offset.inputs['Scale'])
    rugged=N.new('GeometryNodeSetPosition'); L.new(ico.outputs[0],rugged.inputs[0]); L.new(offset.outputs[0],rugged.inputs['Offset'])
    sm=N.new('GeometryNodeSetMaterial'); sm.inputs['Material'].default_value=ice_material(name+'_Mat',local=True)
    L.new(rugged.outputs[0],sm.inputs['Geometry'])
    ins=N.new('GeometryNodeInstanceOnPoints'); L.new(gi.outputs[0],ins.inputs['Points']); L.new(sm.outputs[0],ins.inputs['Instance'])
    for nm,socket in [('scale','Scale'),('rot','Rotation')]:
        at=N.new('GeometryNodeInputNamedAttribute'); at.data_type='FLOAT_VECTOR'; at.inputs['Name'].default_value=nm
        L.new(at.outputs[0],ins.inputs[socket])
    L.new(ins.outputs[0],go.inputs[0]); ob.modifiers.new(name,'NODES').node_group=ng
    return ob


def ice_grain(name='Grain',radius=1,location=(0,0,0),seed=7):
    """Отдельная увеличенная льдинка: гранёная, без каменной текстуры и металлического блеска."""
    # Идеализированный осколок с плоскими сколами и притуплёнными кромками.
    rng=np.random.default_rng(seed); verts=[]
    for z,r,phase in [(-.75,.64,.10),(-.18,1,0),(.7,.74,.16)]:
        for i in range(8):
            a=i*math.tau/8+phase; rr=r*rng.uniform(.9,1.10)
            verts.append((radius*rr*math.cos(a),radius*rr*math.sin(a)*.78,radius*(z+rng.uniform(-.07,.07))))
    faces=[tuple(range(7,-1,-1)),tuple(range(16,24))]
    for j in range(2):
        for i in range(8): faces.append((j*8+i,j*8+(i+1)%8,(j+1)*8+(i+1)%8,(j+1)*8+i))
    me=bpy.data.meshes.new(name+'_Mesh'); me.from_pydata(verts,[],faces); me.update()
    ob=bpy.data.objects.new(name,me); C.link(ob,'Enceladus'); ob.location=location
    bevel=ob.modifiers.new('SoftIceEdges','BEVEL'); bevel.width=radius*.055; bevel.segments=3
    mat,N,L,out=C.new_material(name+'_Mat')
    bs=N.new('ShaderNodeBsdfPrincipled')
    bs.inputs['Base Color'].default_value=(.84,.94,1,1)
    bs.inputs['Roughness'].default_value=.08; bs.inputs['IOR'].default_value=1.31
    bs.inputs['Transmission Weight'].default_value=.93
    tc=N.new('ShaderNodeTexCoord'); no=N.new('ShaderNodeTexNoise')
    no.inputs['Scale'].default_value=12; no.inputs['Detail'].default_value=3
    L.new(tc.outputs['Generated'],no.inputs['Vector'])
    rough=N.new('ShaderNodeMapRange'); rough.inputs['To Min'].default_value=.04; rough.inputs['To Max'].default_value=.14
    L.new(no.outputs['Fac'],rough.inputs[0]); L.new(rough.outputs[0],bs.inputs['Roughness'])
    bump=N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.12; bump.inputs['Distance'].default_value=radius*.012
    L.new(no.outputs['Fac'],bump.inputs['Height']); L.new(bump.outputs[0],bs.inputs['Normal'])
    vol=N.new('ShaderNodeVolumeScatter'); vol.inputs['Color'].default_value=(.6,.8,.94,1)
    vol.inputs['Density'].default_value=.035/radius; vol.inputs['Anisotropy'].default_value=.25
    L.new(vol.outputs[0],out.inputs['Volume'])
    L.new(bs.outputs[0],out.inputs['Surface']); ob.data.materials.append(mat)
    return ob
