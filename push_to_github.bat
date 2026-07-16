@echo off
echo =====================================================
echo   AI Sales OS - Push to GitHub for Render Deploy
echo =====================================================

cd /d "%~dp0"

:: Check if git is initialized
if not exist ".git" (
    echo Initializing git repository...
    git init
    git remote add origin https://github.com/dheeraj73406-eng/AI-Sales-Agent.git
)

echo.
echo Staging all files...
git add -A

echo.
echo Committing...
git commit -m "chore: prepare for Render Free deployment"

echo.
echo Pushing to GitHub...
git push -u origin main

echo.
echo =====================================================
echo   Done! Now go to render.com and deploy.
echo =====================================================
pause
