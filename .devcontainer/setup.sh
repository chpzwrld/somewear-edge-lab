#!/usr/bin/env bash
# Installs the course's dependencies. Safe to re-run: bash .devcontainer/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"

echo "[*] Installing network tools..."
$SUDO apt-get update -qq
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    iproute2 iputils-ping netcat-openbsd tcpdump socat procps diffutils >/dev/null

echo "[*] Installing Python libraries..."
python3 -m pip install -q --disable-pip-version-check -r requirements.txt

chmod +x course.py launch.sh simulator/*.py tools/*.py tests/*.py tests/*.sh lab/*.sh 2>/dev/null || true
echo "[+] Ready! Start with:  python3 course.py lesson 0"
