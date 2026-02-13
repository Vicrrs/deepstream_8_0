#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${RTSP_HOST:-127.0.0.1}"
PORT="${RTSP_PORT:-8554}"
CAM_COUNT="${CAM_COUNT:-37}"
COLS="${MOSAIC_COLS:-7}"
ROWS="${MOSAIC_ROWS:-6}"
TILE_W="${TILE_W:-320}"
TILE_H="${TILE_H:-180}"
TRANSPORT="${RTSP_TRANSPORT:-tcp}"

if ! command -v ffplay >/dev/null 2>&1; then
  echo "Erro: ffplay nao encontrado. Instale ffmpeg/ffplay e tente novamente."
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  echo "Subindo rtsp-server (docker compose up -d rtsp-server)..."
  docker compose up -d rtsp-server >/dev/null
fi

max_slots=$((COLS * ROWS))
if (( CAM_COUNT > max_slots )); then
  echo "Aviso: CAM_COUNT=${CAM_COUNT} maior que grade ${COLS}x${ROWS}=${max_slots}."
  echo "Serao exibidas apenas ${max_slots} cameras."
  CAM_COUNT="${max_slots}"
fi

inputs=()
chains=()
layout_parts=()

for i in $(seq 1 "$CAM_COUNT"); do
  cam_id="$(printf 'video%02d' "$i")"
  url="rtsp://${HOST}:${PORT}/${cam_id}"
  inputs+=( -rtsp_transport "$TRANSPORT" -i "$url" )

  x=$(( ((i - 1) % COLS) * TILE_W ))
  y=$(( ((i - 1) / COLS) * TILE_H ))

  chains+=( "[$((i - 1)):v]setpts=PTS-STARTPTS,scale=${TILE_W}:${TILE_H}[v$((i - 1))]" )
  layout_parts+=( "${x}_${y}" )
done

xstack_inputs=""
for i in $(seq 0 $((CAM_COUNT - 1))); do
  xstack_inputs+="[v${i}]"
done

IFS=';'; chains_joined="${chains[*]}"; unset IFS
IFS='|'; layout="${layout_parts[*]}"; unset IFS

filter_complex="${chains_joined};${xstack_inputs}xstack=inputs=${CAM_COUNT}:layout=${layout}[vout]"

echo "Abrindo mosaico ${COLS}x${ROWS} com ${CAM_COUNT} cameras..."
exec ffplay -hide_banner -loglevel warning -fflags nobuffer -flags low_delay -an \
  "${inputs[@]}" \
  -filter_complex "$filter_complex" \
  -map "[vout]"
