"""Shared Blender helpers for the MakeHuman template (run inside Blender)."""
import addon_utils, bpy
import numpy as np
from mathutils import Vector


def enable_mpfb():
    """Enable the MPFB extension (MakeHuman for Blender, https://github.com/makehumancommunity/mpfb2) and return
    its package name. Install it once in Blender (Edit > Preferences > Get Extensions, or Install from Disk)."""
    import importlib
    for mod in addon_utils.modules(refresh=True):
        if mod.__name__.split('.')[-1] == 'mpfb':
            addon_utils.enable(mod.__name__, default_set=True)
            return mod.__name__
    raise RuntimeError('MPFB (MakeHuman) Blender extension not found: install MPFB 2.0.18 or newer in Blender')


def _turn(rig, pb, target):
    """rotate pose bone pb so that its world direction becomes `target`"""
    bpy.context.view_layer.update()
    cur = (rig.matrix_world.to_3x3() @ (pb.tail - pb.head)).normalized()
    q = cur.rotation_difference(target.normalized())
    M = pb.matrix.to_3x3()
    pb.rotation_mode = 'QUATERNION'
    pb.rotation_quaternion = (M.inverted() @ q.to_matrix() @ M).to_quaternion() @ pb.rotation_quaternion
    bpy.context.view_layer.update()


def bone(rig, name):
    return rig.pose.bones.get('mixamorig:' + name) or rig.pose.bones.get(name)


def pose_photo(rig, targets):
    """the photo T-pose: each limb aimed at points measured on the photo hull (Blender frame, metres, already at
    the template's scale): upper arm, forearm and hand on the line shoulder -> wrist; thigh -> knee, shin -> ankle"""
    for side in ('Left', 'Right'):
        t = targets[side]
        shoulder = rig.matrix_world @ bone(rig, side + 'Arm').head
        line = Vector(t['wrist']) - shoulder
        for name in ('Arm', 'ForeArm', 'Hand'):
            _turn(rig, bone(rig, side + name), line)
        _turn(rig, bone(rig, side + 'UpLeg'), Vector(t['knee']) - rig.matrix_world @ bone(rig, side + 'UpLeg').head)
        _turn(rig, bone(rig, side + 'Leg'), Vector(t['ankle']) - rig.matrix_world @ bone(rig, side + 'Leg').head)
