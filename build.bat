@echo off
chcp 65001 >nul
title Build GrokVideoGenerator - Nuitka
echo ============================================
echo   GrokVideoGenerator - Nuitka Build Script
echo ============================================
echo.

:: Check Python
python --version 2>nul
if errorlevel 1 (
    echo [ERROR] Python khong tim thay! Cai Python 3.13 truoc.
    pause
    exit /b 1
)

:: Get CPU count for max parallel jobs
for /f "tokens=2 delims==" %%a in ('wmic cpu get NumberOfLogicalProcessors /value ^| find "="') do set CPU_COUNT=%%a
set CPU_COUNT=%CPU_COUNT: =%
if "%CPU_COUNT%"=="" set CPU_COUNT=4
echo [INFO] CPU cores: %CPU_COUNT%
echo.

:: Step 1: Install dependencies
echo [1/4] Cai dat dependencies...
echo ----------------------------------------
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
pip install httpcore certifi anyio sniffio h11 idna
pip install urllib3 charset-normalizer
pip install cffi pycparser
pip install nuitka ordered-set zstandard
if errorlevel 1 (
    echo [ERROR] Cai dat dependencies that bai!
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

:: Step 2: Verify imports
echo [2/4] Kiem tra imports...
echo ----------------------------------------
python verify_imports.py
if errorlevel 1 (
    echo [ERROR] Import check failed! Xem log phia tren.
    pause
    exit /b 1
)
echo.

:: Step 3: Find grapheme data path
echo [3/4] Tim grapheme data path...
echo ----------------------------------------
for /f "delims=" %%p in ('python -c "import grapheme,os; print(os.path.dirname(grapheme.__file__))"') do set GRAPHEME_DIR=%%p
echo grapheme dir: %GRAPHEME_DIR%

if exist "%GRAPHEME_DIR%\data" (
    echo [OK] grapheme/data found
    dir "%GRAPHEME_DIR%\data\*.json"
) else (
    echo [WARN] grapheme/data NOT found, build may fail
)

:: Find curl_cffi dir (contains native .dll)
for /f "delims=" %%p in ('python -c "import curl_cffi,os; print(os.path.dirname(curl_cffi.__file__))"') do set CURL_CFFI_DIR=%%p
echo curl_cffi dir: %CURL_CFFI_DIR%
echo.

:: Step 4: Build with Nuitka
echo [4/4] Building with Nuitka (jobs=%CPU_COUNT%)...
echo ----------------------------------------
echo Build bat dau luc: %date% %time%
echo.

python -m nuitka ^
    --standalone ^
    --onefile ^
    --windows-console-mode=force ^
    --output-filename=GrokVideoGenerator.exe ^
    --enable-plugin=pyside6 ^
    --jobs=%CPU_COUNT% ^
    --include-package=src ^
    --include-package=src.core ^
    --include-package=src.gui ^
    --include-package=httpx ^
    --include-package=httpcore ^
    --include-package=anyio ^
    --include-package=anyio._backends ^
    --include-package=requests ^
    --include-package=urllib3 ^
    --include-package=charset_normalizer ^
    --include-package=curl_cffi ^
    --include-package=pydantic ^
    --include-package=pydantic.deprecated ^
    --include-package=cryptography ^
    --include-package=cryptography.hazmat ^
    --include-package=cryptography.hazmat.primitives ^
    --include-package=cryptography.hazmat.backends ^
    --include-package=selenium ^
    --include-package=selenium.webdriver ^
    --include-package=selenium.webdriver.common ^
    --include-package=selenium.webdriver.chrome ^
    --include-package=undetected_chromedriver ^
    --include-package=chromedriver_autoinstaller ^
    --include-package=setuptools ^
    --include-package=setuptools._distutils ^
    --include-package=setuptools._distutils.version ^
    --include-package=zendriver ^
    --include-package=zendriver.core ^
    --include-package=zendriver.cdp ^
    --include-package=websockets ^
    --include-package=websockets.legacy ^
    --include-package=emoji ^
    --include-package=grapheme ^
    --include-package=latest_user_agents ^
    --include-package=user_agents ^
    --include-module=_cffi_backend ^
    --include-module=sqlite3 ^
    --include-module=ctypes ^
    --include-module=platform ^
    --include-module=hashlib ^
    --include-module=base64 ^
    --include-module=PySide6.QtMultimedia ^
    --include-module=PySide6.QtMultimediaWidgets ^
    --include-package-data=PySide6 ^
    --include-package-data=certifi ^
    --include-package-data=cryptography ^
    --include-package-data=pydantic ^
    --include-package-data=zendriver ^
    --include-package-data=emoji ^
    --include-package-data=grapheme ^
    --include-package-data=curl_cffi ^
    --include-package-data=charset_normalizer ^
    --include-package-data=selenium ^
    --include-package-data=undetected_chromedriver ^
    --include-package-data=setuptools ^
    --include-package-data=latest_user_agents ^
    --include-package-data=user_agents ^
    --include-package-data=chromedriver_autoinstaller ^
    --include-data-dir="%GRAPHEME_DIR%\data=grapheme/data" ^
    --include-data-dir="%CURL_CFFI_DIR%=curl_cffi" ^
    --nofollow-import-to=tkinter ^
    --nofollow-import-to=_tkinter ^
    --nofollow-import-to=PyQt6 ^
    --nofollow-import-to=PyQt5 ^
    --nofollow-import-to=PySide2 ^
    --nofollow-import-to=matplotlib ^
    --nofollow-import-to=numpy ^
    --nofollow-import-to=pandas ^
    --nofollow-import-to=scipy ^
    --nofollow-import-to=IPython ^
    --nofollow-import-to=jupyter ^
    --nofollow-import-to=wx ^
    --nofollow-import-to=kivy ^
    --nofollow-import-to=test ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=doctest ^
    --nofollow-import-to=giaima ^
    --no-pyi-file ^
    --assume-yes-for-downloads ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build that bai!
    echo Kiem tra log phia tren de biet loi.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   BUILD THANH CONG!
echo ============================================
if exist GrokVideoGenerator.exe (
    for %%A in (GrokVideoGenerator.exe) do echo File: %%~fA  Size: %%~zA bytes
) else (
    echo [WARN] File GrokVideoGenerator.exe khong tim thay o thu muc hien tai
    echo Tim kiem...
    dir /s /b GrokVideoGenerator.exe 2>nul
)
echo.
echo Build xong luc: %date% %time%
pause
