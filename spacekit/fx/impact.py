"""Направленный каменный выброс: GN-инстансы, ключи времени, без симулятора/драйверов.

Кинематическая реконструкция, не гидрокод. Метры, фиксированный seed, полый конус.
"""
import math
import random
import bpy
from mathutils import Vector
from .. import anim
from .. import core as C


def build_ejecta(name, origin, direction, rock_meshes, count=9000, seed=6,
                speed=(1.5,22.0), size=(.035,1.3), cone_deg=(28,64), parent=None):
    """rock_meshes — меши/объекты прототипов. Возвращает root/object/time_node."""
    rng=random.Random(seed)
    axis=Vector(direction).normalized()
    u=axis.cross(Vector((0,0,1)))
    u=u.normalized() if u.length>.01 else Vector((1,0,0))
    v=axis.cross(u).normalized()
    verts,vel,scales,rots,variants=[],[],[],[],[]
    for i in range(count):
        theta=math.radians(rng.uniform(*cone_deg)); phi=rng.uniform(0,math.tau)
        d=axis*math.cos(theta)+(u*math.cos(phi)+v*math.sin(phi))*math.sin(theta)
        a=size[0]*(size[1]/size[0])**(rng.random()**3.4)
        vel.extend(d*rng.uniform(*speed))
        verts.append(tuple(u*rng.uniform(-1.7,1.7)+v*rng.uniform(-1.7,1.7)))
        scales.extend((a,a*rng.uniform(.6,1.2),a*rng.uniform(.55,1)))
        rots.extend(rng.uniform(0,math.tau) for _ in range(3)); variants.append(i%len(rock_meshes))
    me=bpy.data.meshes.new(name+'_Points'); me.from_pydata(verts,[],[])
    for nm,typ,field,values in [('velocity','FLOAT_VECTOR','vector',vel),('scale','FLOAT_VECTOR','vector',scales),
                              ('rot','FLOAT_VECTOR','vector',rots),('variant','INT','value',variants)]:
        at=me.attributes.new(nm,typ,'POINT'); at.data.foreach_set(field,values)
    root=C.empty(name+'_Root',coll='Impact',parent=parent,loc=origin)
    ob=bpy.data.objects.new(name,me); C.link(ob,'Impact'); ob.parent=root
    templates=bpy.data.collections.new(name+'_Templates')
    for i,proto in enumerate(rock_meshes):
        mesh=proto.data if hasattr(proto,'data') else proto
        templates.objects.link(bpy.data.objects.new(name+'_Rock'+str(i),mesh))
    ng=bpy.data.node_groups.new(name+'_GN','GeometryNodeTree')
    ng.interface.new_socket('Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    N,L=ng.nodes,ng.links
    gi,go=N.new('NodeGroupInput'),N.new('NodeGroupOutput')
    clock=N.new('ShaderNodeValue'); clock.name='AgeSeconds'; clock.outputs[0].default_value=0.
    def attr(nm,typ='FLOAT_VECTOR'):
        a=N.new('GeometryNodeInputNamedAttribute'); a.data_type=typ; a.inputs['Name'].default_value=nm
        return a.outputs['Attribute']
    move=N.new('ShaderNodeVectorMath'); move.operation='SCALE'
    L.new(attr('velocity'),move.inputs[0]); L.new(clock.outputs[0],move.inputs['Scale'])
    sp=N.new('GeometryNodeSetPosition'); L.new(gi.outputs['Geometry'],sp.inputs['Geometry'])
    L.new(move.outputs['Vector'],sp.inputs['Offset'])
    ci=N.new('GeometryNodeCollectionInfo'); ci.transform_space='ORIGINAL'
    ci.inputs['Collection'].default_value=templates
    ci.inputs['Separate Children'].default_value=True; ci.inputs['Reset Children'].default_value=True
    ip=N.new('GeometryNodeInstanceOnPoints'); ip.inputs['Pick Instance'].default_value=True
    L.new(sp.outputs['Geometry'],ip.inputs['Points']); L.new(ci.outputs['Instances'],ip.inputs['Instance'])
    L.new(attr('variant','INT'),ip.inputs['Instance Index']); L.new(attr('scale'),ip.inputs['Scale'])
    er=N.new('FunctionNodeEulerToRotation'); L.new(attr('rot'),er.inputs['Euler'])
    L.new(er.outputs['Rotation'],ip.inputs['Rotation'])
    L.new(C.math_node(N,L,'GREATER_THAN',clock.outputs[0],.0001),ip.inputs['Selection'])
    L.new(ip.outputs['Instances'],go.inputs['Geometry']); ob.modifiers.new('Ejecta','NODES').node_group=ng
    return dict(root=root,object=ob,time_node=clock,templates=templates)


def key_age(ejecta,keys):
    """[(кадр,возраст_с),…]. Отрицательный возраст скрывает выброс."""
    sock=ejecta['time_node'].outputs[0]
    for f,age in keys:
        sock.default_value=age; sock.keyframe_insert('default_value',frame=f)
    anim.set_interpolation(ejecta['time_node'].id_data,'LINEAR')
