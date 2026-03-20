import tkinter as tk

from ip_camera_viewer.ui.main_window import MainWindow


def run() -> None:
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
