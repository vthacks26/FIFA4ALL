#!/usr/bin/env bash
# Download the MediaPipe FaceLandmarker model bundle used by the vision layer.
# Idempotent: skips the download if the file already exists.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${ROOT_DIR}/models"
MODEL_PATH="${MODEL_DIR}/face_landmarker.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"

mkdir -p "${MODEL_DIR}"
if [ -s "${MODEL_PATH}" ]; then
  echo "==> Model already present: ${MODEL_PATH}"
  exit 0
fi

echo "==> Downloading FaceLandmarker model to ${MODEL_PATH}"
curl -sSL -o "${MODEL_PATH}" "${MODEL_URL}"
echo "==> Downloaded $(du -h "${MODEL_PATH}" | cut -f1)"
