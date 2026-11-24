import os, shutil, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), 'body3d')
sys.path.insert(0, PKG)


def find_blender():
    for c in [os.environ.get('BLENDER'), shutil.which('blender'), '/opt/homebrew/bin/blender',
              '/Applications/Blender.app/Contents/MacOS/Blender']:
        if c and os.path.exists(c):
            return c
    return None


@pytest.fixture(scope='session')
def blender():
    b = find_blender()
    if not b:
        pytest.skip('找不到 Blender')
    return b


@pytest.fixture(scope='session')
def model_glb():
    p = os.environ.get('BODY3D_GLB', os.path.join(HERE, 'data', 'body_rigged.glb'))
    if not os.path.exists(p):
        pytest.skip(f'沒有測試模型 {p}')
    return p


@pytest.fixture(scope='session')
def synth_set(blender, model_glb, tmp_path_factory):
    """33 張乾淨的合成照片（由測試模型在 Blender 正交渲染），整個測試只渲染一次"""
    out = tmp_path_factory.mktemp('synth') / 'set'
    subprocess.run([blender, '-b', '--factory-startup', '--python', os.path.join(HERE, 'render_synth.py'), '--',
                    model_glb, str(out)], check=True, capture_output=True)
    assert len(os.listdir(out)) == 33
    return out


@pytest.fixture(scope='session')
def persp_set(blender, model_glb, tmp_path_factory):
    """同一個模型，但用距離 4 m 的透視相機渲染（違反「正交 / 長焦距」規範）"""
    out = tmp_path_factory.mktemp('persp') / 'set'
    subprocess.run([blender, '-b', '--factory-startup', '--python', os.path.join(HERE, 'render_synth.py'), '--',
                    model_glb, str(out), '4.0'], check=True, capture_output=True)
    assert len(os.listdir(out)) == 33
    return out


def run_py(script, *args, cwd=None, timeout=1800):
    """run a package script with this interpreter; returns (exit code, stdout+stderr)"""
    p = subprocess.run([sys.executable, os.path.join(PKG, script), *map(str, args)], cwd=cwd,
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def lines(out, level):
    return [l for l in out.splitlines() if l.strip().startswith(f'[{level}]')]
