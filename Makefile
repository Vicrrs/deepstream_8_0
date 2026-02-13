# Makefile - deepstream_7_1
# Uso:
#   make up
#   make run CAM=video01 MODEL=EPI
#   make run CAM=video03 MODEL=Hall RTSP_PORT=9003 UDP_PORT=5403
#   make watch RTSP_PORT=9001 RTSP_MOUNT=/cam
#   make down

SHELL := /bin/bash

# --- Compose / serviços ---
COMPOSE ?= docker compose
COMPOSE_FILE ?= docker-compose.yaml
DEEPSTREAM_SVC ?= deepstream
RTSP_SVC ?= rtsp-server
TRITON_SVC ?= triton

# --- Parâmetros do run.py (defaults) ---
CAM ?= video01
MODEL ?= EPI

RTSP_IN_HOST ?= 127.0.0.1
RTSP_IN_PORT ?= 8554
RTSP_IN_URI  ?= rtsp://$(RTSP_IN_HOST):$(RTSP_IN_PORT)/$(CAM)

RTSP_PORT ?= 9000
RTSP_MOUNT ?= /ds-mosaic
UDP_PORT ?= 5400

CODEC ?= H264
BITRATE ?= 4000000

# Caminho do "config-file-path" do nvinfer (no seu caso: /app/models/<MODEL>/<arquivo>.txt)
# Ajuste se o arquivo dentro da pasta do modelo tiver outro nome.
PGIE_CONFIG ?= /app/models/$(MODEL)/$(shell echo $(MODEL) | tr '[:upper:]' '[:lower:]').txt

# Se seus arquivos não seguem essa regra (epi.txt, hall.txt, etc),
# melhor usar um mapa explícito:
# PGIE_CONFIG = /app/models/$(MODEL)/$(MODEL).txt  (ex: EPI.txt não existe)
# Então vou deixar um fallback manual por MODEL abaixo.
define MAP_MODEL
$(if $(filter $(MODEL),EPI),/app/models/EPI/epi.txt,\
$(if $(filter $(MODEL),Hall),/app/models/Hall/hall.txt,\
$(if $(filter $(MODEL),person),/app/models/person/person.txt,\
/app/models/$(MODEL)/$(MODEL).txt)))
endef
PGIE_CONFIG := $(MAP_MODEL)

# --- Helpers ---
deepstream_cid = $(shell $(COMPOSE) -f $(COMPOSE_FILE) ps -q $(DEEPSTREAM_SVC))

.PHONY: help up down ps logs restart-rtsp sh run watch run-multi stop

help:
	@echo "Targets:"
	@echo "  make up                     # docker compose up --build -d"
	@echo "  make down                   # docker compose down"
	@echo "  make ps                     # status"
	@echo "  make logs SVC=deepstream    # logs -f"
	@echo "  make restart-rtsp           # reinicia rtsp-server"
	@echo "  make sh                     # bash no container deepstream"
	@echo "  make run CAM=video01 MODEL=EPI"
	@echo "  make watch RTSP_PORT=9000 RTSP_MOUNT=/ds-mosaic"
	@echo ""
	@echo "Vars úteis:"
	@echo "  CAM=video01 MODEL=EPI RTSP_PORT=9000 UDP_PORT=5400 CODEC=H264 BITRATE=4000000"
	@echo "  COMPOSE_FILE=docker-compose_arm64_ubuntu22.yml"

up:
	$(COMPOSE) -f $(COMPOSE_FILE) up --build -d

down:
	$(COMPOSE) -f $(COMPOSE_FILE) down

ps:
	$(COMPOSE) -f $(COMPOSE_FILE) ps

logs:
	@if [ -z "$(SVC)" ]; then echo "Use: make logs SVC=deepstream|rtsp-server|triton|web"; exit 1; fi
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f --tail=200 $(SVC)

restart-rtsp:
	$(COMPOSE) -f $(COMPOSE_FILE) restart $(RTSP_SVC)

sh:
	$(COMPOSE) -f $(COMPOSE_FILE) exec -it $(DEEPSTREAM_SVC) bash

# Roda 1 câmera com 1 modelo (single pipeline).
# Requisitos: seu run.py aceitar --pgie-config (ver nota abaixo).
run: up
	@if [ -z "$(call deepstream_cid)" ]; then echo "Deepstream container não encontrado. Rode: make up"; exit 1; fi
	@echo ">> CAM=$(CAM)  MODEL=$(MODEL)"
	@echo ">> INPUT=$(RTSP_IN_URI)"
	@echo ">> PGIE_CONFIG=$(PGIE_CONFIG)"
	@echo ">> RTSP out: rtsp://127.0.0.1:$(RTSP_PORT)$(RTSP_MOUNT) (udp $(UDP_PORT))"
	$(COMPOSE) -f $(COMPOSE_FILE) exec -it $(DEEPSTREAM_SVC) bash -lc '\
		cd /app && \
		python3 run.py \
			-i "$(RTSP_IN_URI)" \
			--pgie-config "$(PGIE_CONFIG)" \
			-c "$(CODEC)" -b "$(BITRATE)" \
			--rtsp-port "$(RTSP_PORT)" --rtsp-mount "$(RTSP_MOUNT)" --udp-port "$(UDP_PORT)" \
	'

watch:
	ffplay -fflags nobuffer -flags low_delay -rtsp_transport tcp rtsp://127.0.0.1:$(RTSP_PORT)$(RTSP_MOUNT)

stop:
	$(COMPOSE) -f $(COMPOSE_FILE) stop
