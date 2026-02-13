from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import time
import threading
import json
from urllib.request import urlopen
from pathlib import Path
import os
import cv2

app = FastAPI()
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
CROPS_DIR = Path("/app/crops")
if CROPS_DIR.exists():
    app.mount("/crops", StaticFiles(directory=CROPS_DIR), name="crops")

# Cada camera pode ter "url" direto ou "candidates" para fallback.
RTSP_HOST = os.getenv("RTSP_HOST", "127.0.0.1")
CAMERA_DEFS = [
    ("video01", "DCS1 Escada"),
    ("video02", "DCS1 Rampa entrada"),
    ("video03", "DCS1 Recepcao"),
    ("video04", "DCS1 Delivery"),
    ("video05", "DCS1 Portao 1"),
    ("video06", "DCS1 Facilities"),
    ("video07", "DCS1 Deposito 2"),
    ("video08", "Perimetro Telco"),
    ("video09", "DCS1 Subestacao P7"),
    ("video10", "DCS1 Subestacao P5"),
    ("video11", "DCS1 Doca Externo"),
    ("video12", "DCS1 Subestacao P1"),
    ("video13", "DCS1 Sala UPS"),
    ("video14", "DCS1 Corredor Perimetro 1"),
    ("video15", "DCS1 Telco"),
    ("video16", "DCS1 Acesso Containers"),
    ("video17", "DCS1 Subestacao Portas"),
    ("video18", "DCS1 Recepcao 2"),
    ("video19", "DCS1 Patio Fisheye"),
    ("video20", "DCS1 Engenharia Redes"),
    ("video21", "DCS1 Clausura"),
    ("video22", "DCS1 Doca Cortina"),
    ("video23", "DCS1 Corredor Doca"),
    ("video24", "DCS1 IPFIBRA"),
    ("video25", "DCS1 Financeiro"),
    ("video26", "DCS1 Deposito Doca Externo"),
    ("video27", "DCS1 Guarita"),
    ("video28", "DCS1 Frente Esquerda"),
    ("video29", "DCS1 Container Externo"),
    ("video30", "DCS1 Perimetro 2"),
    ("video31", "DCS1 Aquario"),
    ("video32", "DCS1 SR01-CAM3"),
    ("video33", "DCS1 SR01-CAM2"),
    ("video34", "DCS1 Geradores"),
    ("video35", "DCS1 SR01-CAM1"),
    ("video36", "DCS1 SGTI"),
    ("video37", "DCS1 Doca Interno"),
]

def _port_for(cam_id: str, base: int) -> int:
    try:
        idx = int(cam_id.replace("video", ""))
    except Exception:
        idx = 0
    return base + idx

RTSP_SOURCES = []
for cam_id, label in CAMERA_DEFS:
    rtsp_port = _port_for(cam_id, 9000)
    metrics_port = _port_for(cam_id, 10000)
    RTSP_SOURCES.append(
        {
            "id": cam_id,
            "label": label,
            "url": f"rtsp://{RTSP_HOST}:{rtsp_port}/ds-{cam_id}",
            "metrics_url": f"http://{RTSP_HOST}:{metrics_port}/metrics",
        }
    )

stats_lock = threading.Lock()
stats = {}
for source in RTSP_SOURCES:
    cam_id = source["id"]
    stats[cam_id] = {
        "fps": 0.0,
        "status": "offline",
        "url": source.get("url"),
        "label": source.get("label", cam_id),
        "labels": {},
        "label_order": [],
    }


# FUNCOES AUXILIARES
def find_working_rtsp(candidates):
    """Procura o primeiro RTSP que abre com sucesso."""
    for url in candidates:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            print(f"RTSP ativo detectado: {url}")
            cap.release()
            return url
        else:
            print(f"Falha ao abrir: {url}")
    raise RuntimeError("Nenhum stream RTSP valido encontrado.")


def open_capture(url):
    import cv2
    # Tenta GStreamer primeiro; se falhar, cai para FFMPEG.
    gst = (
        f"rtspsrc location={url} protocols=tcp latency=100 ! "
        "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! "
        "appsink drop=1 max-buffers=1 sync=false"
    )
    cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
    if cap.isOpened():
        return cap
    cap.release()

    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _poll_label_metrics():
    while True:
        for source in RTSP_SOURCES:
            cam_id = source["id"]
            metrics_url = source.get("metrics_url")
            if not metrics_url:
                continue
            try:
                with urlopen(metrics_url, timeout=0.6) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                counts = data.get("counts", {}).get("total", {})
                order = data.get("label_order", [])
                with stats_lock:
                    stats[cam_id]["labels"] = counts
                    stats[cam_id]["label_order"] = order
            except Exception:
                with stats_lock:
                    stats[cam_id]["labels"] = {}
                    stats[cam_id]["label_order"] = []
        time.sleep(1.0)


_metrics_thread = threading.Thread(target=_poll_label_metrics, daemon=True)
_metrics_thread.start()


# STREAM
def generate_frames(cam_id):
    import cv2
    """Gera frames JPEG (MJPEG) com calculo de FPS e suporte a fallback."""
    source = next((s for s in RTSP_SOURCES if s["id"] == cam_id), None)
    if source is None:
        raise RuntimeError(f"Camera '{cam_id}' nao encontrada.")

    cap = None
    backoff = 0.5
    prev_time = time.time()
    frame_count = 0
    rtsp_url = source.get("url")

    while True:
        if cap is None or not cap.isOpened():
            try:
                if rtsp_url is None:
                    rtsp_url = find_working_rtsp(source.get("candidates", []))
            except RuntimeError:
                print("Nenhum stream RTSP acessivel. Tentando novamente...")
                with stats_lock:
                    stats[cam_id]["status"] = "offline"
                time.sleep(3)
                continue

            cap = open_capture(rtsp_url)
            if not cap.isOpened():
                time.sleep(backoff)
                backoff = min(backoff * 2, 5)
                cap.release()
                cap = None
                with stats_lock:
                    stats[cam_id]["status"] = "offline"
                continue
            backoff = 0.5
            with stats_lock:
                stats[cam_id]["status"] = "online"
                stats[cam_id]["url"] = rtsp_url

        ok, frame = cap.read()
        if not ok or frame is None:
            print("Perda de conexao com RTSP. Reabrindo...")
            cap.release()
            cap = None
            with stats_lock:
                stats[cam_id]["status"] = "offline"
            continue

        # Se estiver usando um stream sem overlay, desenha uma bbox generica
        if rtsp_url and "video02" in rtsp_url:
            h, w, _ = frame.shape
            bbox = (int(w * 0.3), int(h * 0.3), int(w * 0.3), int(h * 0.4))
            cv2.rectangle(frame, bbox, (0, 255, 0), 2)

        # Calcula FPS
        frame_count += 1
        curr_time = time.time()
        elapsed = curr_time - prev_time
        if elapsed >= 1.0:
            with stats_lock:
                stats[cam_id]["fps"] = frame_count / elapsed
            frame_count = 0
            prev_time = curr_time

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        )



@app.get("/")
def index():
    """Pagina principal (HTML estatico)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/config")
def config():
    payload = []
    for source in RTSP_SOURCES:
        cam_id = source["id"]
        payload.append(
            {
                "id": cam_id,
                "label": source.get("label", cam_id),
                "url": source.get("url"),
            }
        )
    return JSONResponse({"cameras": payload})


@app.get("/crops")
def crops_index():
    index_file = CROPS_DIR / "index.json"
    if not index_file.exists():
        return JSONResponse({"items": []})
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse({"items": []})


@app.get("/video_feed/{cam_id}")
def video_feed(cam_id: str):
    """Endpoint MJPEG."""
    return StreamingResponse(
        generate_frames(cam_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/metrics")
def metrics():
    """Retorna FPS e status."""
    with stats_lock:
        payload = {cam_id: stats[cam_id].copy() for cam_id in stats}
    return JSONResponse(payload)


if __name__ == "__main__":
    print("Servidor iniciado em http://127.0.0.1:8083")
    uvicorn.run(app, host="0.0.0.0", port=8083)
