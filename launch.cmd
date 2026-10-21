@echo off
rem Launch the Somewear Edge Lab course in Docker on Windows.
rem Double-click this file, or run it from a Command Prompt / PowerShell window.
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker is required: https://docs.docker.com/get-docker/
    pause
    exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
    echo Docker is installed but not running. Start Docker Desktop, wait for it to say "running", then try again.
    pause
    exit /b 1
)

docker ps --format "{{.Names}}" | findstr /x "somewear-edge-lab" >nul
if not errorlevel 1 (
    echo The course is already running - opening another terminal in it.
    docker exec -it -w /course somewear-edge-lab bash
    exit /b
)

echo [*] Building the course environment (first time takes a minute or two)...
docker build -q -t somewear-edge-lab . >nul
if errorlevel 1 (
    echo The build failed - see the messages above.
    pause
    exit /b 1
)
echo [*] Starting. Type 'exit' to leave. Your work is saved in this folder.
docker run --rm -it --privileged --name somewear-edge-lab -v "%cd%":/course -w /course somewear-edge-lab
