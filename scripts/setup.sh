#!/usr/bin/env bash
# Idempotent development environment bootstrap for FIFA4ALL.
#
# Safe to run repeatedly: it only installs what is missing and never launches a
# long-running process. Intended to be used as the Cloud Agent `install` step
# and locally by developers.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# --- 1. System libraries -----------------------------------------------------
# MediaPipe's native bindings need OpenGL/EGL at import time, even headless.
# python3-venv is required to create the virtual environment on Debian/Ubuntu.
SYS_PKGS=(python3-venv python3-dev libegl1 libgl1 libglib2.0-0 libgles2 libopengl0)
if command -v apt-get >/dev/null 2>&1; then
  SUDO=""
  if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
  fi
  if [ -n "${SUDO}" ] || [ "$(id -u)" -eq 0 ]; then
    echo "==> Installing system packages: ${SYS_PKGS[*]}"
    ${SUDO} apt-get update -qq
    ${SUDO} apt-get install -y -qq "${SYS_PKGS[@]}"
  else
    echo "WARNING: no root/sudo available; assuming system libs already present." >&2
  fi
else
  echo "WARNING: apt-get not found; skipping system package install." >&2
fi

# --- 2. Python virtual environment -------------------------------------------
if [ ! -x ".venv/bin/python" ]; then
  echo "==> Creating virtual environment (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing Python dependencies"
python -m pip install --upgrade pip -q
python -m pip install -q -r requirements.txt

# --- 3. Vision model bundle --------------------------------------------------
bash scripts/download_models.sh

echo "==> Setup complete. Activate with: source .venv/bin/activate"
python -c "import cv2, mediapipe, numpy; print('cv2', cv2.__version__, '| mediapipe', mediapipe.__version__, '| numpy', numpy.__version__)"
