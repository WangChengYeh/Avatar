"""MakeHuman template, step 4 (Blender): attach the baked textures and export the skinned GLB (Mixamo bone names
without prefix, photo T-pose as rest pose).
    blender -b --python mh_export.py -- WORK_DIR OUT.glb"""
import sys, bpy
D, GLB = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=D + '/uvmesh.blend')
ob = bpy.data.objects['Body']; me = ob.data
for g, name in ((0, 'Body'), (1, 'Head')):
    img = bpy.data.images.load(D + f'/texture_{g}.jpg'); img.pack()
    mat = me.materials[g]; mat.name = name; mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        nt.nodes.clear(); bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = nt.nodes.new('ShaderNodeOutputMaterial'); nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.75
for o in list(bpy.data.objects):
    if o.name not in ('Body', 'Armature'):
        bpy.data.objects.remove(o)
mw = ob.matrix_world.copy()                  # skinned mesh at the root (glTF validator NODE_SKINNED_MESH_NON_ROOT)
ob.parent = None; ob.matrix_world = mw
bpy.ops.export_scene.gltf(filepath=GLB, export_format='GLB', export_image_format='AUTO', export_yup=True,
                          export_skins=True, export_animations=False, export_morph=False)
print('mh_export:', GLB)
