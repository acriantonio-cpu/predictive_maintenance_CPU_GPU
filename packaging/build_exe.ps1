# Costruisce dist\hwdrift-gui.exe (PowerShell, da una venv con le dipendenze bloccate).
#   pip install --require-hashes -r requirements\dev.lock ; pip install --no-deps -e .
# Se PowerShell blocca lo script (criteri di esecuzione):
#   powershell -ExecutionPolicy Bypass -File .\packaging\build_exe.ps1
$ErrorActionPreference = "Stop"
$env:SOURCE_DATE_EPOCH = "1767225600"     # timestamp fisso (build più riproducibile)

# Sorgenti hardware opzionali: senza di esse l'exe non legge GPU NVIDIA (pynvml) né i
# contatori/registro eventi di Windows (pywin32). Vanno installate PRIMA di PyInstaller.
pip install "nvidia-ml-py>=12.535" "pywin32>=306"
python -c "import pynvml, win32pdh, win32evtlog; print('moduli hardware presenti')"

pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\hwdrift-gui.spec
Get-FileHash dist\hwdrift-gui.exe -Algorithm SHA256 | Tee-Object dist\hwdrift-gui.exe.sha256
