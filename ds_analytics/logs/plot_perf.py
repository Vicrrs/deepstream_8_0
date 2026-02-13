#!/usr/bin/env python3
import argparse
import csv
import math
import os
import re
from statistics import mean


def _read_perf_csv(path):
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV sem header")
        ts = []
        gpu = []
        vram_used = []
        vram_total = []
        vram_pct = []
        meta_cols = {"ts_epoch", "gpu_pct", "vram_used_mb", "vram_total_mb", "vram_pct"}
        fps_cols = [c for c in reader.fieldnames if c not in meta_cols]
        fps = {c: [] for c in fps_cols}

        for row in reader:
            try:
                t = float(row.get("ts_epoch", ""))
                g = float(row.get("gpu_pct", ""))
            except Exception:
                continue
            ts.append(t)
            gpu.append(g)
            try:
                vram_used.append(float(row.get("vram_used_mb", "nan")))
            except Exception:
                vram_used.append(float("nan"))
            try:
                vram_total.append(float(row.get("vram_total_mb", "nan")))
            except Exception:
                vram_total.append(float("nan"))
            try:
                vram_pct.append(float(row.get("vram_pct", "nan")))
            except Exception:
                vram_pct.append(float("nan"))
            for c in fps_cols:
                try:
                    fps[c].append(float(row.get(c, "nan")))
                except Exception:
                    fps[c].append(float("nan"))

    if not ts:
        raise ValueError("CSV sem dados numéricos")
    return ts, gpu, fps, vram_used, vram_total, vram_pct


def _mean_ignore_nan(values):
    vals = [v for v in values if not math.isnan(v)]
    return mean(vals) if vals else 0.0


def _series_mean(fps, cols):
    if not cols:
        return []
    n = len(next(iter(fps.values())))
    out = []
    for i in range(n):
        vals = [fps[c][i] for c in cols]
        out.append(_mean_ignore_nan(vals))
    return out


def _pick_stream_cols(fps_cols):
    stream_cols = [c for c in fps_cols if c.startswith("stream")]
    return stream_cols if stream_cols else fps_cols


def _glob_logs(path):
    if os.path.isdir(path):
        base = path
    else:
        base = os.path.dirname(path) or "."
    files = []
    for name in os.listdir(base):
        if name.startswith("perf_") and name.endswith(".csv"):
            files.append(os.path.join(base, name))
    return sorted(files)


def _parse_cams_from_name(path):
    name = os.path.basename(path)
    m = re.search(r"perf_(\\d+)cams_", name)
    if m:
        return int(m.group(1))
    return None


def _summary_stats(ts, gpu, fps, stream_cols, vram_pct):
    avg_fps_series = _series_mean(fps, stream_cols)
    avg_fps = _mean_ignore_nan(avg_fps_series)
    avg_gpu = _mean_ignore_nan(gpu)
    avg_vram_pct = _mean_ignore_nan(vram_pct)
    n = max(1, len(stream_cols))
    avg_gpu_per_cam = avg_gpu / n
    duration_s = max(0.0, ts[-1] - ts[0]) if ts else 0.0
    return {
        "avg_fps": avg_fps,
        "avg_gpu": avg_gpu,
        "avg_vram_pct": avg_vram_pct,
        "avg_gpu_per_cam": avg_gpu_per_cam,
        "streams": len(stream_cols),
        "duration_s": duration_s,
    }


def main():
    ap = argparse.ArgumentParser(description="Gera gráficos de GPU e FPS a partir do perf_*.csv")
    ap.add_argument("csv_or_dir", help="Caminho do perf_*.csv ou diretório de logs")
    ap.add_argument("-o", "--out", default=None, help="Caminho do PNG de saída (somente 1 CSV)")
    ap.add_argument("--max-bars", type=int, default=32, help="Máx de streams no gráfico de barras")
    ap.add_argument("--per-file", action="store_true", help="Quando for diretório, gera PNG por CSV também")
    args = ap.parse_args()

    inputs = []
    if os.path.isdir(args.csv_or_dir):
        inputs = _glob_logs(args.csv_or_dir)
    else:
        inputs = [args.csv_or_dir]

    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib não está instalado. Instale e rode novamente.")
        print("Exemplo: pip install matplotlib")
        return 2

    summaries = []
    for csv_path in inputs:
        ts, gpu, fps, vram_used, vram_total, vram_pct = _read_perf_csv(csv_path)
        fps_cols = list(fps.keys())
        stream_cols = _pick_stream_cols(fps_cols)

        t0 = ts[0]
        t = [x - t0 for x in ts]
        avg_fps = _series_mean(fps, stream_cols)
        gpu_per_cam = [g / max(1, len(stream_cols)) for g in gpu]

        # médias por stream para barras
        fps_means = {c: _mean_ignore_nan(fps[c]) for c in stream_cols}
        # limitar para legibilidade
        items = sorted(fps_means.items(), key=lambda kv: kv[0])
        if args.max_bars and len(items) > args.max_bars:
            items = items[: args.max_bars]

        stats = _summary_stats(ts, gpu, fps, stream_cols, vram_pct)
        stats["csv_path"] = csv_path
        stats["cams_from_name"] = _parse_cams_from_name(csv_path)
        summaries.append(stats)

        if len(inputs) == 1 or args.per_file:
            out = args.out
            if not out or len(inputs) > 1:
                base, _ = os.path.splitext(csv_path)
                out = base + "_summary.png"

            plt.style.use("seaborn-v0_8")
            has_vram = any(not math.isnan(v) for v in vram_pct)
            rows = 4 if has_vram else 3
            fig = plt.figure(figsize=(14, 3.1 * rows), dpi=120)

            # 1) GPU vs FPS médio
            ax1 = fig.add_subplot(rows, 1, 1)
            ax1.plot(t, gpu, color="#d62728", label="GPU %")
            ax1.set_ylabel("GPU (%)")
            ax1.grid(True, alpha=0.3)
            ax1b = ax1.twinx()
            ax1b.plot(t, avg_fps, color="#1f77b4", label="FPS médio (streams)")
            ax1b.set_ylabel("FPS médio")
            ax1.set_title("GPU vs FPS médio")

            # 2) GPU por câmera
            ax2 = fig.add_subplot(rows, 1, 2)
            ax2.plot(t, gpu_per_cam, color="#2ca02c")
            ax2.set_ylabel("GPU % por câmera")
            ax2.set_xlabel("Tempo (s)")
            ax2.grid(True, alpha=0.3)
            ax2.set_title(f"GPU por câmera (N={len(stream_cols)})")

            if has_vram:
                # 3) VRAM
                ax3 = fig.add_subplot(rows, 1, 3)
                ax3.plot(t, vram_pct, color="#ff7f0e")
                ax3.set_ylabel("VRAM (%)")
                ax3.set_xlabel("Tempo (s)")
                ax3.grid(True, alpha=0.3)
                ax3.set_title("VRAM (%)")
                bars_row = 4
            else:
                bars_row = 3

            # Barras: FPS médio por stream
            ax4 = fig.add_subplot(rows, 1, bars_row)
            labels = [k for k, _ in items]
            values = [v for _, v in items]
            ax4.bar(labels, values, color="#9467bd")
            ax4.set_ylabel("FPS médio")
            ax4.set_xlabel("Stream")
            ax4.set_title("FPS médio por stream")
            ax4.tick_params(axis="x", rotation=60)
            ax4.grid(axis="y", alpha=0.3)

            fig.tight_layout()
            fig.savefig(out)
            plt.close(fig)
            print(f"OK: {out}")

    # resumo combinado quando for diretório
    if len(inputs) > 1:
        combined_out = args.out or os.path.join(os.path.dirname(inputs[0]) or ".", "perf_all_summary.png")
        # ordena por número de câmeras (fallback para streams)
        def _key(s):
            return s["cams_from_name"] if s["cams_from_name"] is not None else s["streams"]

        summaries.sort(key=_key)
        xs = [s["cams_from_name"] if s["cams_from_name"] is not None else s["streams"] for s in summaries]
        fps_avg = [s["avg_fps"] for s in summaries]
        gpu_avg = [s["avg_gpu"] for s in summaries]
        gpu_cam = [s["avg_gpu_per_cam"] for s in summaries]
        vram_avg = [s["avg_vram_pct"] for s in summaries]

        plt.style.use("seaborn-v0_8")
        has_vram = any(v > 0.0 for v in vram_avg)
        rows = 3 if has_vram else 2
        fig = plt.figure(figsize=(14, 3.6 * rows), dpi=120)

        ax1 = fig.add_subplot(rows, 1, 1)
        ax1.plot(xs, fps_avg, marker="o", color="#1f77b4", label="FPS médio")
        ax1.set_ylabel("FPS médio")
        ax1.grid(True, alpha=0.3)
        ax1.set_title("Resumo: FPS médio vs número de câmeras")

        ax2 = fig.add_subplot(rows, 1, 2)
        ax2.plot(xs, gpu_avg, marker="o", color="#d62728", label="GPU % médio")
        ax2.plot(xs, gpu_cam, marker="o", color="#2ca02c", label="GPU % por câmera")
        ax2.set_xlabel("Número de câmeras")
        ax2.set_ylabel("GPU (%)")
        ax2.grid(True, alpha=0.3)
        ax2.set_title("Resumo: GPU médio e GPU por câmera")
        ax2.legend()

        if has_vram:
            ax3 = fig.add_subplot(rows, 1, 3)
            ax3.plot(xs, vram_avg, marker="o", color="#ff7f0e", label="VRAM % médio")
            ax3.set_xlabel("Número de câmeras")
            ax3.set_ylabel("VRAM (%)")
            ax3.grid(True, alpha=0.3)
            ax3.set_title("Resumo: VRAM médio")

        fig.tight_layout()
        fig.savefig(combined_out)
        plt.close(fig)
        print(f"OK: {combined_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
