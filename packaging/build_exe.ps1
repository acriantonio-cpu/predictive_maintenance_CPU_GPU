# Costruisce dist\hwdrift-gui.exe (PowerShell, da una venv con le dipendenze bloccate).
#   pip install --require-hashes -r requirements\dev.lock ; pip install --no-deps -e .
$ErrorActionPreference = "Stop"
$env:SOURCE_DATE_EPOCH = "1767225600"     # timestamp fisso (build più riproducibile)
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\hwdrift-gui.spec
Get-FileHash dist\hwdrift-gui.exe -Algorithm SHA256 | Tee-Object dist\hwdrift-gui.exe.sha256
