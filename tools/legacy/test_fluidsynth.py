import os
import sys

bin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vendor", "fluidsynth-bin", "fluidsynth-v2.6.1-win10-x64-cpp11", "bin"))
os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
os.environ["FLUIDSYNTH_LIB"] = os.path.join(bin_dir, "libfluidsynth-3.dll")

import fluidsynth

print("pyfluidsynth imported successfully")
fs = fluidsynth.Synth(gain=1.5)
print(f"Synth created: {fs}")
methods = [m for m in dir(fs) if not m.startswith("_")]
print(f"Synth methods: {methods}")
