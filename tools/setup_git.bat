@echo off
setlocal EnableExtensions

rem ---------------------------------------------------------------------------
rem One-time repo setup for Hollow Tide. Safe to run again: finished steps are skipped.
rem   1. rename _github -> .github
rem   2. git init (branch main) + first commit
rem   3. optional: create a PRIVATE GitHub repo with GitHub CLI (gh) and push
rem ---------------------------------------------------------------------------

cd /d "%~dp0.."
echo Repo folder: %CD%
echo.

where git >nul 2>nul
if errorlevel 1 goto :no_git

rem --- 1. .github folder ------------------------------------------------------
if not exist "_github" goto :github_dir_done
if exist ".github" goto :github_dir_both
ren "_github" ".github"
if errorlevel 1 goto :rename_failed
echo [OK] Renamed _github to .github
goto :github_dir_done
:github_dir_both
echo [WARN] Both _github and .github exist. Left them unchanged; merge them by hand.
:github_dir_done

rem --- 2. git repo + first commit ---------------------------------------------
if exist ".git" goto :have_repo
git init -b main
if errorlevel 1 goto :git_failed
:have_repo

git rev-parse --verify HEAD >nul 2>nul
if not errorlevel 1 goto :already_committed

set "GITNAME="
set "GITMAIL="
for /f "delims=" %%A in ('git config user.name 2^>nul') do set "GITNAME=%%A"
for /f "delims=" %%A in ('git config user.email 2^>nul') do set "GITMAIL=%%A"
if defined GITNAME goto :name_ok
set /p "GITNAME=Name to use for git commits: "
git config user.name "%GITNAME%"
:name_ok
if defined GITMAIL goto :mail_ok
set /p "GITMAIL=Email to use for git commits: "
git config user.email "%GITMAIL%"
:mail_ok

git add -A
if errorlevel 1 goto :git_failed

set "MSG=%TEMP%\hollowtide_commit_msg.txt"
> "%MSG%" echo M0/M1: minimal loadable mod, tooling and docs
>>"%MSG%" echo.
>>"%MSG%" echo - mod/: modinfo, modmain, strings en/zh, debug hooks, placeholder tide_crystal
>>"%MSG%" echo - tools/: check_mod.py, art/prepare_icon.py, link_mod.bat, setup_git.bat
>>"%MSG%" echo - docs/: phase 1 plan, testing, tide altar design, art pipeline, architecture, API notes
>>"%MSG%" echo - docs/test_reports/2026-10-11: in-game M0/M1 test report
>>"%MSG%" echo.
>>"%MSG%" echo Co-Authored-By: Claude Opus 5.5 ^<noreply@anthropic.com^>
>>"%MSG%" echo Claude-Session: https://claude.ai/code/session_01FmFsHBCbFtVGQGfKSTmar7
git commit -q -F "%MSG%"
if errorlevel 1 goto :git_failed
del "%MSG%" >nul 2>nul
echo [OK] First commit created.
goto :remote

:already_committed
echo [INFO] The repo already has commits. Skipping the first commit; commit new changes as usual.

rem --- 3. GitHub ---------------------------------------------------------------
:remote
echo.
git remote get-url origin >nul 2>nul
if not errorlevel 1 goto :push_existing
where gh >nul 2>nul
if errorlevel 1 goto :no_gh
choice /c YN /m "Create a PRIVATE GitHub repo named hollow-tide and push to it"
if errorlevel 2 goto :summary
gh auth status >nul 2>nul
if not errorlevel 1 goto :gh_ready
echo You are not logged in to GitHub CLI. Follow the prompts; a browser window will open.
gh auth login --web --git-protocol https
if errorlevel 1 goto :gh_failed
:gh_ready
gh repo create hollow-tide --private --source . --remote origin --push
if errorlevel 1 goto :gh_failed
echo [OK] Pushed to a private GitHub repo.
goto :summary

:push_existing
echo Remote "origin" is already set. Pushing...
git push -u origin main
if errorlevel 1 goto :gh_failed
goto :summary

:no_gh
echo [INFO] GitHub CLI (gh) not found. To push manually:
echo        1. Create an EMPTY private repo on github.com
echo        2. git remote add origin https://github.com/YOUR_NAME/hollow-tide.git
echo        3. git push -u origin main
goto :summary

:gh_failed
echo [ERROR] GitHub step failed. See the message above. The local repo is fine.
goto :summary

:no_git
echo [ERROR] git was not found. Install Git for Windows, then run this again.
goto :end

:rename_failed
echo [ERROR] Could not rename _github. Is the folder open in another program?
goto :end

:git_failed
echo [ERROR] A git command failed. See the message above.
goto :summary

:summary
echo.
echo ---- git status ----
git status -sb
echo ---- last commits ----
git log --oneline -3
echo ---- remotes ----
git remote -v

:end
echo.
endlocal
pause
