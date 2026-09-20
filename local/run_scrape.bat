@echo off
REM Scrape Lelongtips from this PC and push the result to GitHub.
REM
REM The site only accepts the login from the network it was created on, so
REM the scrape has to happen here. Everything after that — rebuilding the
REM database, the dashboard and the Telegram alert — runs on GitHub once
REM this pushes the snapshot.
REM
REM First-time setup is in local/README.md.

cd /d "%~dp0\.."

if "%LELONGTIPS_COOKIE%"=="" (
  echo.
  echo LELONGTIPS_COOKIE is not set. See local\README.md.
  echo.
  pause
  exit /b 1
)

set INCLUDE_EXPIRED=true
set SNAPSHOT_ONLY=true

echo Scraping (this takes about 35 minutes)...
python src\monitor.py
if errorlevel 1 (
  echo.
  echo Scrape failed. Most likely the session cookie expired -- log in to
  echo lelongtips.com.my again, copy a fresh lt_session, and update it.
  echo.
  pause
  exit /b 1
)

echo Pushing the snapshot to GitHub...
git add data/snapshots
git commit -m "Scrape from local machine %date% %time%"
git push

echo.
echo Done. GitHub will rebuild the database and send your Telegram alert.
pause
