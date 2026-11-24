import os


def pytest_addoption(parser):
    parser.addoption('--photos', default=os.environ.get('BODY3D_PHOTOS'),
                     help='33 張照片資料夾：給了才跑完整端到端測試（約 3 分鐘）')
