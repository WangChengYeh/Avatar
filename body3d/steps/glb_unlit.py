"""Mark every material of a GLB as KHR_materials_unlit (photo textures already contain lighting)."""
import json, struct, sys

src, dst = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read()
magic, ver, length = struct.unpack('<4sII', data[:12])
assert magic == b'glTF'
off = 12
chunks = []
while off < len(data):
    clen, ctype = struct.unpack('<I4s', data[off:off + 8])
    chunks.append([ctype, data[off + 8:off + 8 + clen]])
    off += 8 + clen
assert chunks[0][0] == b'JSON'
gl = json.loads(chunks[0][1].decode().rstrip(' \x00'))
for m in gl.get('materials', []):
    m.setdefault('extensions', {})['KHR_materials_unlit'] = {}
    pbr = m.setdefault('pbrMetallicRoughness', {})
    pbr['metallicFactor'] = 0.0
    pbr['roughnessFactor'] = 1.0
used = set(gl.get('extensionsUsed', [])) | {'KHR_materials_unlit'}
gl['extensionsUsed'] = sorted(used)
js = json.dumps(gl, separators=(',', ':')).encode()
js += b' ' * ((4 - len(js) % 4) % 4)
chunks[0][1] = js
body = b''.join(struct.pack('<I4s', len(c), t) + c for t, c in chunks)
open(dst, 'wb').write(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)
print('unlit materials:', len(gl.get('materials', [])))
