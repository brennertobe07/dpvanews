@echo off
REM va_pulse/run_daily.bat
REM Daily refresh: fetch RSS -> analyze themes -> render HTML -> (later) git push.
REM Designed to be invoked by Windows Task Scheduler.
REM
REM PREREQUISITES (one-time):
REM   1. Python 3 installed and on PATH.
REM   2. pip install -r requirements.txt
REM   3. Anthropic API key stored as a persistent user env var:
REM        setx ANTHROPIC_API_KEY "sk-ant-..."
REM      (close and reopen cmd after running setx for it to take effect)
REM   4. For git push (later): GitHub Pages repo cloned at C:\DPVAnews\output
REM      and configured with credentials that don't prompt.

setlocal
cd /d C:\DPVAnews\output\pipeline

echo.
echo ============================================================
echo  VA PULSE - Daily refresh - %DATE% %TIME%
echo ============================================================

echo.
echo --- [1/4] Fetching RSS feeds ---
python fetch.py
if errorlevel 1 (
  echo ERROR: fetch.py failed. Aborting run.
  endlocal
  exit /b 1
)

echo.
echo --- [2/4] Analyzing themes ---
python analyze.py
if errorlevel 1 (
  echo WARN: analyze.py failed. Continuing so the page still re-renders
  echo       with the most recent items and the previous themes.json.
)

echo.
echo --- [3/4] Rendering HTML ---
python render.py
if errorlevel 1 (
  echo ERROR: render.py failed. Aborting run.
  endlocal
  exit /b 1
)

echo.
echo --- [4/4] Pushing to GitHub Pages ---
cd /d C:\DPVAnews\output
git add -A
git commit -m "Daily refresh %DATE% %TIME%" || echo (nothing to commit)
git push
if errorlevel 1 (
  echo ERROR: git push failed.
  endlocal
  exit /b 1
)

echo.
echo === Daily refresh complete ===
endlocal
exit /b 0
