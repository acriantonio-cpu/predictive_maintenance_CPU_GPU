# SPDX-License-Identifier: Apache-2.0
# PyInstaller: un solo eseguibile senza console (GUI) che accetta anche i comandi della CLI.
#   pyinstaller --noconfirm --clean packaging/hwdrift-gui.spec
# Va eseguito su Windows per ottenere un .exe (PyInstaller non fa cross-compilazione).
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = collect_submodules("hwdrift")  # i collector si importano dinamicamente (importlib)
hidden += ["yaml", "psutil", "scipy.stats", "scipy.special", "scipy._lib.messagestream"]
if sys.platform == "win32":
    hidden += ["win32pdh", "win32evtlog", "pywintypes", "clr", "pynvml"]  # opzionali, se presenti

a = Analysis(
    ["gui_entry.py"],
    pathex=["../src"],
    datas=collect_data_files("hwdrift"),  # regole YAML di diagnosi e configurazione di esempio
    hiddenimports=hidden,
    excludes=["matplotlib", "pandas", "pytest", "hypothesis", "IPython", "PIL", "sphinx",
              "numpy.tests", "scipy.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="hwdrift-gui",
    console=False,          # niente finestra nera; l'output CLI non è visibile (vedi la guida)
    upx=False,              # UPX fa scattare più falsi positivi degli antivirus
    icon=None,
)
