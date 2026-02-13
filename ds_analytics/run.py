#!/usr/bin/env python3
import sys
import argparse
import os
import gi
import re
from datetime import datetime

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib

from common.bus_call import bus_call
from pipeline.builder import PipelineBuilder
from pipeline.rtsp import start_rtsp_server
from metrics_server import start_metrics_server


def parse_args():
    p = argparse.ArgumentParser(description="DeepStream multi-RTSP single pipeline")
    p.add_argument("--pgie-config", default="/app/models/EPI/epi.txt")
    p.add_argument("--labels", default=None, help="Arquivo de labels (override do config)")
    p.add_argument("-i", "--input", nargs="+", required=True)
    p.add_argument("-c", "--codec", default="H264", choices=["H264", "H265"])
    p.add_argument("-b", "--bitrate", default=4_000_000, type=int)
    p.add_argument("--rtsp-port", default="9000")
    p.add_argument("--rtsp-mount", default="/ds-mosaic")
    p.add_argument("--udp-port", type=int, default=5400)
    p.add_argument("--metrics-host", default="0.0.0.0")
    p.add_argument("--metrics-port", type=int, default=None)
    p.add_argument("--perf-csv", default=None, help="Caminho do CSV de performance")
    p.add_argument("--stream-name", default=None, help="Nome do stream para métricas/crops")
    p.add_argument("--gst-debug", default=None)
    return p.parse_args()


def _read_text(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _parse_labels_from_pgie_config(cfg_path: str):
    text = _read_text(cfg_path)
    if not text:
        return None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if "labelfile-path" in s:
            parts = s.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip()
        if "label_filename" in s:
            m = re.search(r'label_filename\\s*:\\s*"?([^"]+)"?', s)
            if m:
                return m.group(1).strip()
    return None


def _load_labels(labels_path: str | None):
    if not labels_path:
        return []
    try:
        with open(labels_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception:
        return []


def _safe_name(text: str):
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-")


def main():
    args = parse_args()

    if args.gst_debug:
        os.environ["GST_DEBUG"] = str(args.gst_debug)

    Gst.init(None)

    labels_path = args.labels or _parse_labels_from_pgie_config(args.pgie_config)
    labels = _load_labels(labels_path)

    stream_names = None
    if args.stream_name:
        stream_names = [args.stream_name]
    elif args.rtsp_mount:
        stream_names = [args.rtsp_mount.lstrip("/").replace("ds-", "")]

    if args.perf_csv:
        perf_csv_path = args.perf_csv
    else:
        cams = len(args.input)
        mount = _safe_name(args.rtsp_mount.lstrip("/") or "mosaic")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        perf_csv_path = f"/app/logs/perf_{cams}cams_{mount}_{ts}.csv"

    builder = PipelineBuilder(
        args.input,
        codec=args.codec,
        bitrate=args.bitrate,
        pgie_config=args.pgie_config,
        labels=labels,
        stream_names=stream_names,
        perf_csv_path=perf_csv_path,
        udp_port=args.udp_port,
    )

    pipeline = builder.build()

    metrics_port = args.metrics_port
    if metrics_port is None:
        try:
            metrics_port = int(args.rtsp_port) + 1000
        except Exception:
            metrics_port = 9100
    start_metrics_server(
        builder.perf,
        host=args.metrics_host,
        port=metrics_port,
        pgie_config=args.pgie_config,
        labels_path=labels_path,
    )

    start_rtsp_server(
        codec=args.codec,
        port=str(args.rtsp_port),
        mount=str(args.rtsp_mount),
        udp_port=int(args.udp_port),
    )

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    builder.schedule_perf_log()
    builder.start()

    print(f">> INPUT: {args.input}")
    print(f">> PGIE: {args.pgie_config}")
    print(f">> RTSP out: rtsp://127.0.0.1:{args.rtsp_port}{args.rtsp_mount}  (udp ingest {args.udp_port})")
    print(f">> METRICS: http://127.0.0.1:{metrics_port}/metrics")
    print(f">> PERF CSV: {perf_csv_path}")

    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            builder.stop()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
