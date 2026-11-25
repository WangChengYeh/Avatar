import os


def pytest_addoption(parser):
    parser.addoption('--photos', default=os.environ.get('BODY3D_PHOTOS'),
                     help='33 張照片資料夾：給了才跑完整端到端測試（約 3 分鐘）')
    parser.addoption('--e2e-synth', action='store_true', default=bool(os.environ.get('BODY3D_E2E_SYNTH')),
                     help='完美合成照片不加 --force 跑完整 18 步（#28，約 25 分鐘）')
    parser.addoption('--e2e-makehuman', action='store_true', default=bool(os.environ.get('BODY3D_E2E_MAKEHUMAN')),
                     help='完美合成照片用 --template makehuman 跑完整 18 步（需 MPFB）')
