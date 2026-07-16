@echo off
echo =====================================================
echo   AI Sales OS - Push to GitHub for Render Deploy
echo =====================================================

cd /d "%~dp0"

:: Check if git is initialized
if not exist ".git" (
    echo Initializing git repository...
    git init
    
    echo.
    echo Please go to GitHub and create an empty repository.
    set /p REPO_URL="Paste your new GitHub Repository URL here (e.g. https://github.com/yourname/repo.git): "
    
    git remote add origin !REPO_URL!
)

:: Check if the user wants to change their remote URL
echo.
echo Current GitHub Repository URL:
git remote -v
echo.
set /p CHANGE_URL="Do you need to change this GitHub URL? (y/n) [n]: "
if /i "%CHANGE_URL%"=="y" (
    set /p NEW_URL="Paste your correct GitHub Repository URL here: "
    git remote set-url origin %NEW_URL%
    echo URL updated!
)

echo.
echo Staging all files...
git add -A

echo.
echo Committing...
git commit -m "update: deployment push"

echo.
echo Pushing to GitHub...
git push -u origin main

if %errorlevel% neq 0 (
    echo.
    echo =====================================================
    echo ERROR: Push failed. This usually happens if:
    echo 1. You haven't logged into GitHub on this computer.
    echo 2. The repository URL is incorrect.
    echo 3. The repository doesn't exist on GitHub.
    echo =====================================================
) else (
    echo.
    echo =====================================================
    echo   Done! Now go to render.com and deploy.
    echo =====================================================
)

pause
