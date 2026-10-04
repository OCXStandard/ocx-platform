@echo off
rem ---------------------------------------------------------------
rem Installs the ocx-validator CLI from a dist zip (cmd.exe version).
rem
rem Usage:
rem   install.bat [path\to\ocx-validator.zip] [install-folder]
rem
rem With no arguments, looks for ocx-validator.zip next to this
rem script and prompts for the install folder.
rem Requires Windows 10 1803+ (uses the built-in tar.exe).
rem ---------------------------------------------------------------
setlocal EnableExtensions

set "ZIP=%~1"
if "%ZIP%"=="" set "ZIP=%~dp0ocx-validator.zip"
if not exist "%ZIP%" (
    echo Zip file not found: %ZIP%
    exit /b 1
)

set "DEFAULT=%LOCALAPPDATA%\Programs\ocx-validator"
set "INSTALLDIR=%~2"
if "%INSTALLDIR%"=="" (
    set /p INSTALLDIR=Install folder [%DEFAULT%]: 
)
if "%INSTALLDIR%"=="" set "INSTALLDIR=%DEFAULT%"

echo Installing ocx-validator to "%INSTALLDIR%" ...
if not exist "%INSTALLDIR%" mkdir "%INSTALLDIR%"
tar -xf "%ZIP%" -C "%INSTALLDIR%"
if errorlevel 1 (
    echo Extraction failed.
    exit /b 1
)

rem If the zip contained a top-level ocx-validator folder, flatten it.
if exist "%INSTALLDIR%\ocx-validator\ocx-validator.exe" if not exist "%INSTALLDIR%\ocx-validator.exe" (
    robocopy "%INSTALLDIR%\ocx-validator" "%INSTALLDIR%" /E /MOVE >nul
)

if not exist "%INSTALLDIR%\ocx-validator.exe" (
    echo ocx-validator.exe not found after extraction - is "%ZIP%" a dist zip?
    exit /b 1
)

rem Add the install dir to the user's PATH (idempotent).
set "USERPATH="
for /f "skip=2 tokens=1,2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USERPATH=%%c"
echo ;%USERPATH%; | find /i ";%INSTALLDIR%;" >nul
if errorlevel 1 (
    if "%USERPATH%"=="" (
        setx Path "%INSTALLDIR%" >nul
    ) else (
        setx Path "%USERPATH%;%INSTALLDIR%" >nul
    )
    echo Added "%INSTALLDIR%" to the user PATH.
) else (
    echo "%INSTALLDIR%" is already on the user PATH.
)

echo.
echo Installed: %INSTALLDIR%\ocx-validator.exe
echo Open a NEW terminal and run: ocx-validator --help
exit /b 0
