# ds_analytics/pipeline/rtsp.py
import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GstRtspServer


def start_rtsp_server(
    codec: str = "H264",
    port: str = "9000",
    mount: str = "/ds-mosaic",
    udp_port: int = 5400,
    payload: int = 96,
    clock_rate: int = 90000,
    jitter_latency_ms: int = 100,
):
    Gst.init(None)

    server = GstRtspServer.RTSPServer.new()
    server.set_service(str(port))

    mounts = server.get_mount_points()
    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_shared(True)

    if codec.upper() == "H264":
        enc_name = "H264"
        depay = "rtph264depay"
        parse = "h264parse config-interval=1"
        pay = f"rtph264pay name=pay0 pt={payload} config-interval=1"
    else:
        enc_name = "H265"
        depay = "rtph265depay"
        parse = "h265parse"
        pay = f"rtph265pay name=pay0 pt={payload} config-interval=1"


    rtp_caps = (
        f"application/x-rtp,media=video,clock-rate={clock_rate},"
        f"encoding-name={enc_name}"
    )

    launch = (
        f"( "
        f"udpsrc port={udp_port} caps=\"{rtp_caps}\" buffer-size=1048576 "
        f"! rtpjitterbuffer latency={jitter_latency_ms} drop-on-latency=true "
        f"! queue "
        f"! {depay} "
        f"! queue "
        f"! {parse} "
        f"! queue "
        f"! {pay} "
        f")"
    )

    factory.set_launch(launch)

    try:
        factory.set_latency(jitter_latency_ms)
    except Exception:
        pass

    mounts.add_factory(mount, factory)
    server.attach(None)

    print(
        f"\n*** RTSP at rtsp://localhost:{port}{mount} "
        f"(ingest UDP:{udp_port} RTP/{enc_name}, served PT={payload}) ***\n"
    )
    return server
