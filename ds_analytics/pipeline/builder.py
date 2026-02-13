# ds_analytics/pipeline/builder.py
import gi
import configparser
import math

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

from .nodes import create_source_bin, make, link_many
from .probes import pgie_src_pad_buffer_probe
from .perf import PerfManager


class PipelineBuilder:
    """
    Pipeline:
      sources -> nvstreammux -> nvinfer -> nvtracker -> nvdsanalytics -> tiler
      -> nvvideoconvert -> nvdsosd -> nvvideoconvert -> capsfilter
      -> encoder -> rtph26xpay -> udpsink (RTP/H264|H265)
    """

    def __init__(
        self,
        uris,
        codec="H264",
        bitrate=4_000_000,
        pgie_config="/app/models/EPI/epi.txt",
        labels=None,
        stream_names=None,
        perf_csv_path="/app/logs/performance.csv",
        udp_port=5400,
        udp_host="127.0.0.1",
        rtp_payload=96,
    ):
        self.uris = uris
        self.codec = codec.upper()
        self.bitrate = int(bitrate)
        self.n = len(uris)

        self.pgie_config = pgie_config
        self.labels = labels or []
        self.stream_names = stream_names or []
        self.perf_csv_path = perf_csv_path

        self.udp_host = udp_host
        self.udp_port = int(udp_port)
        self.rtp_payload = int(rtp_payload)

        self.pipeline = None
        self.perf = None

        if self.n <= 0:
            raise ValueError("Nenhuma URI de entrada fornecida.")
        if self.codec not in ("H264", "H265"):
            raise ValueError("codec deve ser H264 ou H265")

    def _q(self, name: str, max_time_ns: int = 0):
        """
        Queue para estabilizar o pipeline.
        max_time_ns=0 deixa sem limite (default do GStreamer).
        """
        q = make(name, "queue")
        if max_time_ns and max_time_ns > 0:
            q.set_property("max-size-time", int(max_time_ns))
        q.set_property("max-size-buffers", 0)
        q.set_property("max-size-bytes", 0)
        return q

    def _make_encoder(self):
        enc = make("encoder", "nvv4l2h264enc" if self.codec == "H264" else "nvv4l2h265enc")
        enc.set_property("bitrate", self.bitrate)


        for prop, val in [
            ("iframeinterval", 30),
            ("insert-sps-pps", 1),
            ("bufapi-version", 1),
            ("preset-level", 1),
            ("control-rate", 1),
        ]:
            try:
                enc.set_property(prop, val)
            except Exception:
                pass

        for prop, val in [
            ("tuning-info-id", 2),
        ]:
            try:
                enc.set_property(prop, val)
            except Exception:
                pass

        return enc

    def _make_rtppay(self):
        pay = make("rtppay", "rtph264pay" if self.codec == "H264" else "rtph265pay")
        pay.set_property("config-interval", 1)
        pay.set_property("pt", self.rtp_payload)
        return pay

    def _make_udpsink(self):
        sink = make("udpsink", "udpsink")
        sink.set_property("host", self.udp_host)
        sink.set_property("port", self.udp_port)
        sink.set_property("sync", False)
        sink.set_property("async", False)
        try:
            sink.set_property("qos", False)
        except Exception:
            pass
        return sink


    def build(self):
        Gst.init(None)

        p = Gst.Pipeline.new("ds-pipeline")
        self.pipeline = p

        # Perf
        self.perf = PerfManager(
            self.n,
            csv_path=self.perf_csv_path,
            labels=self.labels,
            stream_names=self.stream_names,
        )

        # nvstreammux
        mux = make("streammux", "nvstreammux")
        mux.set_property("width", 640)
        mux.set_property("height", 480)
        mux.set_property("batch-size", self.n)
        mux.set_property("batched-push-timeout", 33000)

        try:
            mux.set_property("live-source", 1)
        except Exception:
            pass

        p.add(mux)

        # Sources -> mux
        for i, uri in enumerate(self.uris):
            src_bin = create_source_bin(i, uri)
            p.add(src_bin)
            sinkpad = mux.request_pad_simple(f"sink_{i}")
            srcpad = src_bin.get_static_pad("src")
            if not srcpad or not sinkpad:
                raise RuntimeError(f"Falha criando pads para source {i} ({uri})")
            if srcpad.link(sinkpad) != Gst.PadLinkReturn.OK:
                raise RuntimeError(f"Falha linkando source {i} no nvstreammux")

        # nvinfer
        # pgie = make("pgie", "nvinfer")
        # pgie.set_property("config-file-path", self.pgie_config)
        
        # pgie (troca automática conforme extensão do arquivo)
        if self.pgie_config.endswith(".pbtxt"):
            pgie = make("pgie", "nvinferserver")
            pgie.set_property("config-file-path", self.pgie_config)
        else:
            pgie = make("pgie", "nvinfer")
            pgie.set_property("config-file-path", self.pgie_config)
            pgie.set_property("batch-size", self.n)

        # tracker
        tracker = make("tracker", "nvtracker")
        cfg = configparser.ConfigParser()
        cfg.read("/app/config/dsnvanalytics_tracker_config.txt")
        if "tracker" in cfg:
            for k in cfg["tracker"]:
                val = cfg.get("tracker", k)
                if k == "tracker-width":
                    tracker.set_property("tracker-width", int(val))
                elif k == "tracker-height":
                    tracker.set_property("tracker-height", int(val))
                elif k == "gpu-id":
                    tracker.set_property("gpu_id", int(val))
                elif k == "ll-lib-file":
                    tracker.set_property("ll_lib_file", val)
                elif k == "ll-config-file":
                    tracker.set_property("ll_config_file", val)

        # analytics (opcional)
        nvanalytics = make("analytics", "nvdsanalytics")
        nvanalytics.set_property("config-file", "/app/config/config_nvdsanalytics.txt")

        # tiler
        tiler = make("tiler", "nvmultistreamtiler")
        rows = int(math.ceil(math.sqrt(self.n)))
        cols = int(math.ceil(self.n / rows))
        tiler.set_property("rows", rows)
        tiler.set_property("columns", cols)
        tiler.set_property("width", 1280)
        tiler.set_property("height", 720)

        # conv + osd + conv + caps
        conv1 = make("conv1", "nvvideoconvert")
        osd = make("osd", "nvdsosd")
        conv2 = make("conv2", "nvvideoconvert")

        caps = make("caps", "capsfilter")
        caps.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))

        # encoder + pay + udpsink
        enc = self._make_encoder()
        pay = self._make_rtppay()
        sink = self._make_udpsink()

        # queues (estabilidade)
        q0 = self._q("q0")
        q1 = self._q("q1")
        q2 = self._q("q2")
        q3 = self._q("q3")
        q4 = self._q("q4")

        # Add elements
        for e in [
            pgie, tracker, nvanalytics, tiler,
            q0, conv1, q1, osd, q2, conv2, q3, caps,
            q4, enc, pay, sink
        ]:
            p.add(e)

        # Link main chain
        link_many(
            mux,
            pgie,
            tracker,
            nvanalytics,
            tiler,
            q0,
            conv1,
            q1,
            osd,
            q2,
            conv2,
            q3,
            caps,
            q4,
            enc,
            pay,
            sink
        )

        # Probe (para perf / analytics no probe)
        pgie_src = pgie.get_static_pad("src")
        if pgie_src:
            pgie_src.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe, self.perf)

        print(f">> UDP out (RTP/{self.codec}) -> {self.udp_host}:{self.udp_port} (pt={self.rtp_payload})")
        return p

    def start(self):
        if not self.pipeline:
            raise RuntimeError("Call build() first")
        self.pipeline.set_state(Gst.State.PLAYING)

    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

    def schedule_perf_log(self):
        # a cada 5s
        GLib.timeout_add(5000, self.perf.snapshot_and_log)
