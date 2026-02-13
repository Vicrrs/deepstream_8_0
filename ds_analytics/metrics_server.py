import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _MetricsHandler(BaseHTTPRequestHandler):
    provider = None
    metadata = None

    def do_GET(self):
        if self.path.rstrip("/") != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        payload = self.provider()
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def start_metrics_server(perf_mgr, host: str, port: int, pgie_config: str, labels_path: str | None):
    def _provider():
        counts = perf_mgr.get_counts()
        return {
            "counts": counts,
            "label_order": list(perf_mgr.label_names),
            "model": {
                "pgie_config": pgie_config,
                "labels_path": labels_path,
            },
            "updated_at": counts.get("updated_at", time.time()),
        }

    handler = type("MetricsHandler", (_MetricsHandler,), {})
    handler.provider = staticmethod(_provider)
    handler.metadata = {
        "pgie_config": pgie_config,
        "labels_path": labels_path,
    }

    httpd = ThreadingHTTPServer((host, int(port)), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
