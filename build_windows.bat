@echo off
REM Build PhenoForge for Windows: creates dist\PhenoForge\PhenoForge.exe and a zip.
REM Needs Python 3.12 (64-bit) from python.org on PATH as "py -3.12".
setlocal
cd /d %~dp0
py -3.12 -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt pyinstaller pytest || goto :error
python -m pytest -q tests || goto :error
pyinstaller packaging\phenoforge.spec --noconfirm || goto :error
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\PhenoForge -DestinationPath dist\PhenoForge-windows-x64.zip" || goto :error
echo.
echo Done: dist\PhenoForge\PhenoForge.exe  (zip: dist\PhenoForge-windows-x64.zip)
exit /b 0
:error
echo Build failed with error %errorlevel%.
exit /b %errorlevel%
