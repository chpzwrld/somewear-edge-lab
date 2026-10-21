#!/usr/bin/env bash
# Launch the Somewear Edge Lab course in Docker.
#   ./launch.sh          build (first time) and open the course terminal
#   ./launch.sh shell    open another terminal in the running course
set -euo pipefail
cd "$(dirname "$0")"

NAME="somewear-edge-lab"
command -v docker >/dev/null || { echo "Docker is required: https://docs.docker.com/get-docker/"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but not running. Start Docker Desktop (or the docker service) and try again."; exit 1; }

if [[ ${1:-} == "shell" ]]; then
    exec docker exec -it -w /course "$NAME" bash
fi

if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "The course is already running - opening another terminal in it."
    exec docker exec -it -w /course "$NAME" bash
fi

echo "[*] Building the course environment (first time takes a minute or two)..."
docker build -q -t "$NAME" . >/dev/null
echo "[*] Starting. Type 'exit' to leave. Your work is saved in this folder."
exec docker run --rm -it --privileged --name "$NAME" -v "$PWD":/course -w /course "$NAME"
