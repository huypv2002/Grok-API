@echo off
chcp 65001 >nul
title Rebuild GrokVideoGenerator - Incremental
echo ============================================
echo   GrokVideoGenerator - Incremental Rebuild
echo ============================================
echo.

:: Get CPU count
for /f "tokens=2 delims==" %%a in ('wmic cpu get NumberOfLogicalProcessors /value ^| find "="') do set CPU_COUNT=%%a
set CPU_COUNT=%CPU_COUNT: =%
if "%CPU_COUNT%"=="" set CPU_COUNT=4
echo [INFO] CPU cores: %CPU_COUNT%

:: Find grapheme data path
for /f "delims=" %%p in ('python -c "import grapheme,os; print(os.path.dirname(grapheme.__file__))"') do set GRAPHEME_DIR=%%p
echo [INFO] grapheme dir: %GRAPHEME_DIR%
echo.

echo [INFO] Rebuilding (incremental)...
echo ----------------------------------------

python -m nuitka ^
    --standalone ^
    --onefile ^
    --windows-console-mode=attach ^
    --output-filename=GrokVideoGenerator.exe ^
    --enable-plugin=pyside6 ^
    --jobs=%CPU_COUNT% ^
    --include-package=src ^
    --include-package=src.core ^
    --include-package=src.gui ^
    --include-package=src.utils ^
    --include-package=httpx ^
    --include-package=httpcore ^
    --include-package=anyio ^
    --include-package=anyio._backends ^
    --include-package=requests ^
    --include-package=urllib3 ^
    --include-package=charset_normalizer ^
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
    --include-package-data=PySide6 ^
    --include-package-data=certifi ^
    --include-package-data=cryptography ^
    --include-package-data=pydantic ^
    --include-package-data=zendriver ^
    --include-package-data=emoji ^
    --include-package-data=grapheme ^
    --include-package-data=charset_normalizer ^
    --include-package-data=selenium ^
    --include-package-data=undetected_chromedriver ^
    --include-package-data=setuptools ^
    --include-package-data=latest_user_agents ^
    --include-package-data=user_users ^
    --include-package-data=chromedriver_autoinstaller ^
    --include-data-dir="%GRAPHEME_DIR%\data=grapheme/data" ^
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
    echo [ERROR] Build that bai!
    pause
    exit /b 1
)

echo.
echo ============================================
if exist GrokVideoGenerator.exe (
    for %%A in (GrokVideoGenerator.exe) do echo BUILD OK! Size: %%~zA bytes
) else (
    echo [WARN] EXE not found in current dir
    dir /s /b GrokVideoGenerator.exe 2>nul
)
echo ============================================
pause
