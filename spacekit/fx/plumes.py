"""Водяные шлейфы Энцелада: разреженный рассеивающий конус и GN-льдинки.

Кинематическая иллюстрация, не газодинамика. Км и секунды; фиксированный seed,
время только ключами. Размер частиц завышен для читаемости, не измерение.
"""
import math
import random

import bpy
from mathutils import Vector
from .. import core as C, anim


def _cone(name,origin,axis,height,width,density,frame_end,time0,time1):
    """Закрытый конус, процедурная плотность плавно гаснет к вершине и бокам."""
    bpy.ops.mesh.primitive_cone_add(vertices=32,radius1=.06,radius2=width,depth=height,
                                   location=Vector(origin)+Vector(axis)*height*.5)
    ob=bpy.context.object; ob.name=name; C.link(ob,'Plumes')
    ob.rotation_mode='QUATERNION'; ob.rotation_quaternion=Vector(axis).to_track_quat('Z','Y')
    mat,N,L,out=C.new_material(name+'_Mat')
    tc=N.new('ShaderNodeTexCoord'); sep=N.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['Generated'],sep.inputs[0])
    noise=N.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=8
    noise.inputs['Detail'].default_value=2; noise.inputs['Roughness'].default_value=.65
    # Дешёвая адвекция 3D-поля вместо дорогого четырёхмерного шума по всему объёму.
    move=N.new('ShaderNodeCombineXYZ')
    for f,t in [(1,time0),(frame_end,time1)]:
        move.inputs['Z'].default_value=-t*.015
        move.inputs['Z'].keyframe_insert('default_value',frame=f)
    anim.set_interpolation(mat.node_tree,'LINEAR',extrapolate='LINEAR')
    advect=N.new('ShaderNodeVectorMath'); advect.operation='ADD'
    L.new(tc.outputs['Generated'],advect.inputs[0]); L.new(move.outputs[0],advect.inputs[1])
    stretch=N.new('ShaderNodeVectorMath'); stretch.operation='MULTIPLY'
    stretch.inputs[1].default_value=(2.8,2.8,.42)
    L.new(advect.outputs[0],stretch.inputs[0]); L.new(stretch.outputs[0],noise.inputs[0])
    end=C.math_node(N,L,'SUBTRACT',1,sep.outputs['Z'])
    end=C.math_node(N,L,'POWER',end,1.35)
    xx=C.math_node(N,L,'SUBTRACT',sep.outputs['X'],.5)
    yy=C.math_node(N,L,'SUBTRACT',sep.outputs['Y'],.5)
    rr=C.math_node(N,L,'ADD',C.math_node(N,L,'MULTIPLY',xx,xx),C.math_node(N,L,'MULTIPLY',yy,yy))
    radius=C.math_node(N,L,'MULTIPLY_ADD',sep.outputs['Z'],.49)
    radius.node.inputs[2].default_value=.01
    radius2=C.math_node(N,L,'MULTIPLY',radius,radius)
    rr=C.math_node(N,L,'DIVIDE',rr,radius2)
    edge=C.math_node(N,L,'EXPONENT',C.math_node(N,L,'MULTIPLY',rr,-6))
    thread=C.math_node(N,L,'POWER',noise.outputs['Fac'],2.2)
    d=C.math_node(N,L,'MULTIPLY',thread,end)
    d=C.math_node(N,L,'MULTIPLY',d,edge)
    d=C.math_node(N,L,'MULTIPLY',d,density)
    scatter=N.new('ShaderNodeVolumeScatter'); scatter.inputs['Color'].default_value=(.83,.9,1,1)
    scatter.inputs['Anisotropy'].default_value=.7
    L.new(d,scatter.inputs['Density']); L.new(scatter.outputs[0],out.inputs['Volume'])
    ob.data.materials.append(mat)
    ob.visible_shadow=False
    return ob


def build_plumes(name,sources,height=60,width=3,count=5000,seed=7,frame_end=600,
                 time0=0,time1=80,density=.035,particle_scale=1,axis=(0,0,1),parent=None):
    rng=random.Random(seed); axis=Vector(axis).normalized()
    root=C.empty(name+'_Root',coll='Plumes',parent=parent)
    u=axis.cross(Vector((0,1,0)))
    u=u.normalized() if u.length>.01 else Vector((1,0,0))
    v=axis.cross(u).normalized()
    volumes=[]
    for j,source in enumerate(sources):
        jet_axis=(axis+u*rng.uniform(-.045,.045)+v*rng.uniform(-.035,.035)).normalized()
        ob=_cone(name+'_V'+str(j),source,jet_axis,height*(.8+.3*rng.random()),width*(.7+.5*rng.random()),density,frame_end,time0,time1)
        ob.parent=root; volumes.append(ob)
    positions=[]; velocities=[]; phases=[]; sizes=[]
    for i in range(count):
        src=Vector(sources[i%len(sources)])
        positions.append(tuple(src+u*rng.gauss(0,.06)+v*rng.gauss(0,.06)))
        speed=rng.uniform(.19,.35)
        vel=axis*speed+u*rng.gauss(0,.008)+v*rng.gauss(0,.008)
        velocities.extend(vel); phases.append(rng.uniform(0,260))
        sizes.append(rng.uniform(.0015,.008)*particle_scale)
    me=bpy.data.meshes.new(name+'_Points'); me.from_pydata(positions,[],[])
    for nm,typ,field,values in [('vel','FLOAT_VECTOR','vector',velocities),('phase','FLOAT','value',phases),
                               ('size','FLOAT','value',sizes)]:
        at=me.attributes.new(nm,typ,'POINT'); at.data.foreach_set(field,values)
    ob=bpy.data.objects.new(name+'_Ice',me); C.link(ob,'Plumes'); ob.parent=root
    ng=bpy.data.node_groups.new(name+'_GN','GeometryNodeTree')
    ng.interface.new_socket('Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    N,L=ng.nodes,ng.links; gi=N.new('NodeGroupInput'); go=N.new('NodeGroupOutput')
    def attr(nm,typ='FLOAT'):
        a=N.new('GeometryNodeInputNamedAttribute'); a.data_type=typ; a.inputs['Name'].default_value=nm
        return a.outputs['Attribute']
    clock=N.new('ShaderNodeValue'); clock.name='FlowSeconds'
    for f,t in [(1,time0),(frame_end,time1)]:
        clock.outputs[0].default_value=t; clock.outputs[0].keyframe_insert('default_value',frame=f)
    age=C.math_node(N,L,'ADD',attr('phase'),clock.outputs[0])
    age=C.math_node(N,L,'MODULO',age,260)
    vel=N.new('ShaderNodeVectorMath'); vel.operation='SCALE'
    L.new(attr('vel','FLOAT_VECTOR'),vel.inputs[0]); L.new(age,vel.inputs['Scale'])
    age2=C.math_node(N,L,'MULTIPLY',age,age)
    dz=C.math_node(N,L,'MULTIPLY',age2,-.000113452*.5)
    grav=N.new('ShaderNodeVectorMath'); grav.operation='SCALE'; grav.inputs[0].default_value=axis
    L.new(dz,grav.inputs['Scale'])
    add=N.new('ShaderNodeVectorMath'); add.operation='ADD'
    L.new(vel.outputs[0],add.inputs[0]); L.new(grav.outputs[0],add.inputs[1])
    sp=N.new('GeometryNodeSetPosition'); L.new(gi.outputs[0],sp.inputs['Geometry'])
    L.new(add.outputs[0],sp.inputs['Offset'])
    ico=N.new('GeometryNodeMeshIcoSphere'); ico.inputs['Radius'].default_value=1; ico.inputs['Subdivisions'].default_value=1
    mat,M,ML,mo=C.new_material(name+'_IceMat')
    bs=M.new('ShaderNodeBsdfPrincipled'); bs.inputs['Base Color'].default_value=(.74,.82,.88,1)
    bs.inputs['Roughness'].default_value=.5; ML.new(bs.outputs[0],mo.inputs['Surface'])
    sm=N.new('GeometryNodeSetMaterial'); sm.inputs['Material'].default_value=mat; L.new(ico.outputs[0],sm.inputs['Geometry'])
    ip=N.new('GeometryNodeInstanceOnPoints'); L.new(sp.outputs[0],ip.inputs['Points'])
    L.new(sm.outputs[0],ip.inputs['Instance']); L.new(attr('size'),ip.inputs['Scale'])
    L.new(ip.outputs[0],go.inputs[0]); ob.modifiers.new(name,'NODES').node_group=ng
    anim.set_interpolation(ng,'LINEAR',extrapolate='LINEAR')
    return dict(root=root,particles=ob,volumes=volumes,clock=clock)
