#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PLAYLIST="streams/rtsp_all_37.m3u"

if ! command -v vlc >/dev/null 2>&1; then
  echo "Erro: vlc nao encontrado. Instale VLC e tente novamente."
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  echo "Subindo rtsp-server (docker compose up -d rtsp-server)..."
  docker compose up -d rtsp-server >/dev/null
fi

echo "Abrindo playlist: ${PLAYLIST}"
exec vlc "$PLAYLIST"
