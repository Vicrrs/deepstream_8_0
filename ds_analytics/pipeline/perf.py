# ds_analytics/pipeline/perf.py
import os, time, threading
from common.gpu_usage import GpuUsage

class _GETFPS:
    def __init__(self):
        self.last = time.time()
        self.count = 0

    def tick(self):
        self.count += 1

    def fps_and_reset(self):
        now = time.time()
        elapsed = max(1e-6, now - self.last)
        fps = round(self.count / elapsed, 2)
        self.count = 0
        self.last = now
        return fps

class PerfManager:
    """Gerencia FPS por stream + uso de GPU + logging CSV + contagem de labels."""
    def __init__(
        self,
        n_streams: int,
        csv_path: str = "/app/logs/performance.csv",
        labels: list | None = None,
        stream_names: list | None = None,
    ):
        self.stream_names = stream_names or []
        self.fps = {self.stream_key(i): _GETFPS() for i in range(n_streams)}
        self.gpu = GpuUsage()
        self.csv_path = csv_path
        self._csv_keys = sorted(self.fps.keys())
        self._csv_header_written = False
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if os.path.exists(self.csv_path):
            os.remove(self.csv_path)
        self.label_names = [l for l in (labels or []) if l]
        self._counts_lock = threading.Lock()
        self._counts_total = self._init_counts()
        self._counts_by_stream = {}
        self._counts_updated_at = 0.0

    def on_frame(self, stream_idx: int):
        self.fps[self.stream_key(stream_idx)].tick()

    def stream_key(self, stream_idx: int):
        if 0 <= stream_idx < len(self.stream_names):
            return self.stream_names[stream_idx]
        return f"stream{stream_idx}"

    def _init_counts(self):
        return {name: 0 for name in self.label_names}

    def label_for_class_id(self, class_id: int):
        if 0 <= class_id < len(self.label_names):
            return self.label_names[class_id]
        return f"class_{class_id}"

    def update_counts(self, counts_by_stream: dict, counts_total: dict):
        with self._counts_lock:
            self._counts_by_stream = counts_by_stream
            self._counts_total = counts_total
            self._counts_updated_at = time.time()

    def get_counts(self):
        with self._counts_lock:
            return {
                "total": dict(self._counts_total),
                "streams": {k: dict(v) for k, v in self._counts_by_stream.items()},
                "updated_at": self._counts_updated_at,
            }

    def snapshot_and_log(self):
        perf = {k: v.fps_and_reset() for k, v in self.fps.items()}
        gpu = self.gpu.get_gpu_utilization()
        print(f"\n**PERF: {perf}, GPU={gpu}%\n")
        if not self._csv_header_written:
            header = "ts_epoch," + ",".join(self._csv_keys) + ",gpu_pct\n"
            with open(self.csv_path, "a") as f:
                f.write(header)
            self._csv_header_written = True
        line = f"{time.time()}," + ",".join(str(perf[k]) for k in self._csv_keys) + f",{gpu}\n"
        with open(self.csv_path, "a") as f:
            f.write(line)
        return True
