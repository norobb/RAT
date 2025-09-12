@echo off
setlocal

echo [INFO] Starting RAT Client build process...

:: --- Configuration ---
set "ICON_FILE=icon.ico"
set "EXE_NAME=client-windows.exe"
set "DIST_PATH=executables"
set "BUILD_PATH=build_temp"

:: --- Validation ---
if not exist "client.py" (
    echo [ERROR] Main script not found: client.py
    goto :error
)
if not exist "%ICON_FILE%" (
    echo [WARNING] Icon file not found: %ICON_FILE%. Building without an icon.
    set "ICON_OPTION="
) else (
    set "ICON_OPTION=--icon=%ICON_FILE%"
)

:: --- Build ---
echo [INFO] Running PyInstaller...
pyinstaller --noconsole --onefile --name "%EXE_NAME%" %ICON_OPTION% --distpath "%DIST_PATH%" --workpath "%BUILD_PATH%" --clean "client.py"

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller failed with error code %errorlevel%.
    goto :error
)

echo [SUCCESS] Executable created successfully in '%DIST_PATH%\%EXE_NAME%'

:: --- Cleanup ---
echo [INFO] Cleaning up temporary build files...
if exist "%BUILD_PATH%" (
    rmdir /s /q "%BUILD_PATH%"
)
if exist "*.spec" (
    del "*.spec"
)

echo [INFO] Build process finished.
goto :eof

:error
echo [FAILED] Build process failed.
exit /b 1

:eof
endlocal
