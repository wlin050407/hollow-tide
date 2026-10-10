@echo off
setlocal

rem ---------------------------------------------------------------------------
rem Link this repo's mod\ folder into Don't Starve Together's mods folder
rem as a directory junction (no admin rights needed).
rem
rem   tools\link_mod.bat                       uses DST_DIR below
rem   tools\link_mod.bat "X:\...\Don't Starve Together"
rem
rem After linking, every file you edit in the repo is what the game loads.
rem ---------------------------------------------------------------------------

set "DST_DIR=D:\Applications\Steam\steamapps\common\Don't Starve Together"
if not "%~1"=="" set "DST_DIR=%~1"
set "MOD_NAME=hollowtide"

for %%I in ("%~dp0..\mod") do set "SRC=%%~fI"
set "TARGET=%DST_DIR%\mods\%MOD_NAME%"

if not exist "%SRC%\modinfo.lua" goto :no_src
if not exist "%DST_DIR%\mods" goto :no_dst
if exist "%TARGET%" goto :already

mklink /J "%TARGET%" "%SRC%"
if errorlevel 1 goto :mklink_failed
echo.
echo [OK] Linked: "%TARGET%"
echo      ---^> "%SRC%"
goto :done

:no_src
echo [ERROR] Cannot find "%SRC%\modinfo.lua". Keep this script inside the repo's tools folder.
goto :done

:no_dst
echo [ERROR] Cannot find "%DST_DIR%\mods".
echo         Pass your DST install folder as the first argument.
goto :done

:already
echo [INFO] "%TARGET%" already exists. Nothing changed.
echo        If it is an old copy instead of a link, delete that folder and run this again.
goto :done

:mklink_failed
echo [ERROR] mklink failed. See the message above.
goto :done

:done
endlocal
if "%~1"=="" pause
