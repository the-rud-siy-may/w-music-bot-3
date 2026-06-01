import os

vlc_path = r"C:\Program Files\VideoLAN\VLC"

os.environ["PATH"] = vlc_path + ";" + os.environ["PATH"]

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(vlc_path)

import vlc

print("VLC imported successfully!")

player = vlc.MediaPlayer()

print("Player created successfully!")