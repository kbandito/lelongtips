@echo off
setlocal
title Lelongtips scrape

REM Scrapes Lelongtips from this PC and pushes the result to GitHub.
REM
REM The site only accepts the login from the network that created it, so the
REM scrape has to run here. Everything after it -- rebuilding the database,
REM the dashboard, the Telegram alert -- happens on GitHub once this pushes.
REM
REM Setup instructions: local\README.md

cd /d "%~dp0.."

REM ---- Python -------------------------------------------------------------
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY where py >nul 2>&1 && set "PY=py"
if not defined PY (
  echo.
  echo Python was not found.
  echo Install it from python.org and tick "Add Python to PATH" during setup.
  echo.
  pause
  exit /b 1
)

REM ---- Cookie file --------------------------------------------------------
REM Read from a file, never from a variable: the cookie contains %% characters
REM and Windows mangles those when expanding variables.
if not exist "local\cookie.txt" (
  echo.
  echo local\cookie.txt is missing.
  echo.
  echo   1. Log in to lelongtips.com.my in Chrome
  echo   2. F12 - Application - Cookies - https://www.lelongtips.com.my
  echo   3. Click lt_session, untick "Show URL-decoded", copy the whole value
  echo   4. Paste it into local\cookie.txt and save
  echo.
  pause
  exit /b 1
)

REM ---- Dependencies -------------------------------------------------------
%PY% -c "import requests, bs4" >nul 2>&1
if errorlevel 1 (
  echo Installing Python packages...
  %PY% -m pip install --quiet -r src\requirements.txt
  if errorlevel 1 (
    echo Could not install the packages. See local\README.md.
    pause
    exit /b 1
  )
)

REM ---- Check the session before spending 35 minutes -----------------------
echo Checking your login...
%PY% src\check_session.py
if errorlevel 2 (
  echo.
  echo Your session is not being accepted, so the scrape would collect no
  echo prices. Log in to lelongtips.com.my again, copy a fresh lt_session
  echo value into local\cookie.txt, and run this again.
  echo.
  pause
  exit /b 1
)
if errorlevel 1 (
  echo.
  echo The check could not complete. Check your internet connection.
  echo.
  pause
  exit /b 1
)

echo.
echo Login OK. Scraping now - this takes about 35 minutes.
echo You can leave it running and use the PC normally.
echo.

set "INCLUDE_EXPIRED=true"
set "SNAPSHOT_ONLY=true"
%PY% src\monitor.py
if errorlevel 1 (
  echo.
  echo The scrape failed. The message above says why.
  echo.
  pause
  exit /b 1
)

REM ---- Push the snapshot --------------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
  echo.
  echo Scrape finished, but Git is not installed so it cannot be uploaded.
  echo The data is saved in data\snapshots\ on this PC.
  echo.
  pause
  exit /b 0
)

echo Uploading the snapshot...
git add data/snapshots
git commit -m "Scrape from local machine" >nul 2>&1
if errorlevel 1 (
  echo Nothing new to upload - the snapshot for today already exists.
) else (
  git push
  if errorlevel 1 (
    echo.
    echo Upload failed. The data is saved locally; run "git push" later.
    echo.
    pause
    exit /b 1
  )
  echo Uploaded. GitHub will rebuild the dashboard and send your Telegram alert.
)

echo.
echo Done.
pause
