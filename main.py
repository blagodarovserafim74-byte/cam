from multiprocessing import freeze_support

from ip_camera_viewer.app import run


if __name__ == "__main__":
    freeze_support()
    run()
