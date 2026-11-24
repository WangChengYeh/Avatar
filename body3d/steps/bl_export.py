"""Attach the baked texture, export GLB, then re-import the GLB and render previews of the file itself."""
import bpy, sys, math
from mathutils import Vector

D, GLB = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=D + '/uvmesh.blend')
ob = bpy.data.objects['Body']; me = ob.data
for g, name in ((0, 'Body'), (1, 'Head')):
    img = bpy.data.images.load(D + f'/texture_{g}.jpg'); img.pack()
    mat = me.materials[g]; mat.name = name; mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        nt.nodes.clear()
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.75
bpy.ops.export_scene.gltf(filepath=GLB, export_format='GLB', export_image_format='AUTO', export_yup=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
s = bpy.context.scene; s.render.engine = 'BLENDER_WORKBENCH'
s.display.shading.show_backface_culling = True
s.render.resolution_x, s.render.resolution_y = 600, 900
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c')); s.collection.objects.link(cam); s.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 1.9
s.world = bpy.data.worlds.new('w'); s.world.color = (1, 1, 1)
shots = {'front': (0, 0), 'three_q': (40, 0), 'side': (90, 0), 'back': (180, 0), 'back_q': (225, 0), 'top': (30, 60)}
for light in ('FLAT', 'STUDIO'):
    s.display.shading.light = light; s.display.shading.color_type = 'TEXTURE'
    for name, (az, el) in shots.items():
        a, e = math.radians(az), math.radians(el)
        t = Vector((0, 0, 0.85))
        cam.location = t + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * 5
        cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
        s.render.filepath = f'{D}/v2_{name}_{light}.png'
        bpy.ops.render.render(write_still=True)
# close-up of the head
cam.data.ortho_scale = 0.45
for name, az in (('head_front', 0), ('head_q', 45), ('head_side', 90)):
    a = math.radians(az); t = Vector((0, 0, 1.5))
    cam.location = t + Vector((math.sin(a), -math.cos(a), 0)) * 5
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
    s.display.shading.light = 'FLAT'
    s.render.filepath = f'{D}/v2_{name}.png'
    bpy.ops.render.render(write_still=True)
print('EXPORTED')
