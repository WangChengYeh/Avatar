"""MediaPipe face mesh (468 landmarks) on the frontal head close-up -> face_lm33.npy (col, row, z in pixels).
The bake uses the landmark outline so the frontal close-up owns the face. Required: without mediapipe the script
exits 1; when no face is found it exits 2 (run_all goes on only with --force).
usage: python face_landmarks.py head_000deg.jpg out.npy"""
import sys
import cv2
import numpy as np

src, out = sys.argv[1], sys.argv[2]
try:
    import mediapipe as mp
except ImportError:
    sys.exit('face_landmarks: mediapipe is required (pip install "mediapipe==0.10.14")')
im = cv2.imread(src)
if im is None:
    sys.exit(f'face_landmarks: cannot read {src}')
h, w = im.shape[:2]
with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=False, min_detection_confidence=0.3) as fm:
    r = fm.process(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
if not r.multi_face_landmarks:
    print(f'face_landmarks: no face found in {src}', file=sys.stderr)
    sys.exit(2)
pts = np.array([[l.x * w, l.y * h, l.z * w] for l in r.multi_face_landmarks[0].landmark])
np.save(out, pts)
print(f'face_landmarks: {len(pts)} points -> {out}')
