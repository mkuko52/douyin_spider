@echo off
setlocal
cd /d "%~dp0"

where git >nul 2>nul || (
  echo [ERROR] Git is not installed or not in PATH.
  pause
  exit /b 1
)

if not exist ".git" (
  echo [ERROR] This updater requires a Git-cloned project.
  echo Clone it with: git clone https://github.com/mkuko52/douyin_spider.git
  pause
  exit /b 1
)

git diff --quiet && git diff --cached --quiet || (
  echo [ERROR] Local code changes found. Commit or discard them before updating.
  pause
  exit /b 1
)

echo Updating douyin_spider...
git pull --ff-only origin main || (
  echo [ERROR] Update failed. See the Git message above.
  pause
  exit /b 1
)

echo.
echo Update complete.
pause
