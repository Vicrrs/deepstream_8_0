#!/usr/bin/env python3
import sys
import math
import time
import argparse
import configparser
import gi
gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import Gst, GLib, GstRtspServer
from common.gpu_usage import GpuUsage

import pyds
from ctypes import c_uint, c_int, c_float
import os

# =============================================================================
# Perf data e classes auxiliares (idêntico ao seu, mas ajustando CSV)
# =============================================================================
class GETFPS:
    def __init__(self, stream_id):
        self.stream_id = stream_id
        self.start_time = time.time()
        self.frame_count = 0

    def update_fps(self):
        self.frame_count += 1

    def get_fps(self):
        end_time = time.time()
        fps = float(self.frame_count / (end_time - self.start_time))
        self.frame_count = 0
        self.start_time = end_time
        return round(fps, 2)

class PERF_DATA:
    def __init__(self, num_streams=1):
        self.perf_dict = {}
        self.all_stream_fps = {}
        for i in range(num_streams):
            self.all_stream_fps[f"stream{i}"] = GETFPS(i)
        
        self.gpu_meter = GpuUsage()

    def perf_print_callback(self):
        self.perf_dict = {
            stream_index: stream.get_fps()
            for (stream_index, stream) in self.all_stream_fps.items()
        }
        gpu_usage = self.gpu_meter.get_gpu_utilization()
        print(f"\n**PERF: {self.perf_dict}, GPU={gpu_usage}%\n")

        log_path = "/app/logs/performance.csv"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        timestamp = time.time()

        fps_values = []
        for stream_key in sorted(self.perf_dict.keys()):
            fps_values.append(str(self.perf_dict[stream_key]))

        csv_line = f"{timestamp}," + ",".join(fps_values) + f",{gpu_usage}\n"

        with open(log_path, "a") as f:
            f.write(csv_line)

        return True
    
    def update_fps(self, stream_index):
        self.all_stream_fps[stream_index].update_fps()


# =============================================================================
# Funções de GStreamer
# =============================================================================

def bus_call(bus, message, loop):
    """Callback de mensagens do bus (EOS, ERROR, etc.)"""
    t = message.type
    if t == Gst.MessageType.EOS:
        sys.stdout.write("End-of-stream\n")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        sys.stderr.write("Warning: %s: %s\n" % (err, debug))
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        sys.stderr.write("Error: %s: %s\n" % (err, debug))
        loop.quit()
    return True


def pgie_src_pad_buffer_probe(pad, info, u_data):
    """Extrai metadados e atualiza FPS."""
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer")
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    perf_data = u_data  # passamos perf_data como user_data

    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        # frame_meta.pad_index nos diz qual fonte (0, 1, 2, ...)
        stream_index = f"stream{frame_meta.pad_index}"
        perf_data.all_stream_fps[stream_index].update_fps()

        l_obj = frame_meta.obj_meta_list
        while l_obj:
            try:
                obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            # se quiser extrair bounding boxes, tracker_id, etc., faça aqui
            try:
                l_obj = l_obj.next
            except StopIteration:
                break

        try:
            l_frame = l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK


def cb_newpad(decodebin, decoder_src_pad, data):
    """Callback de pad-added no decodebin."""
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    # Verifica se é vídeo
    if gstname.find("video") != -1:
        if features.contains("memory:NVMM"):
            # Linka decodebin src -> ghost pad
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                print("Failed to link decoder src pad to source bin ghost pad")
        else:
            print("Decodebin did not pick nvidia decoder plugin.")


def decodebin_child_added(child_proxy, Object, name, user_data):
    """Callback ao criar elementos internos do decodebin."""
    print("Decodebin child added:", name)
    if name.find("decodebin") != -1:
        Object.connect("child-added", decodebin_child_added, user_data)


def create_source_bin(index, uri):
    """Cria um bin com decodebin para uma fonte RTSP ou arquivo."""
    bin_name = f"source-bin-{index:02d}"
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        print("Unable to create source bin")
        return None

    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", f"uri-decode-bin-{index}")
    if not uri_decode_bin:
        print("Unable to create uri decode bin")
        return None

    uri_decode_bin.set_property("uri", uri)
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC)
    nbin.add_pad(bin_pad)
    return nbin


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description='DeepStream Multiple RTSP Inputs in Single Pipeline')
    parser.add_argument("-i", "--input", nargs="+", required=True,
                        help="RTSP URLs ou caminhos de vídeos. Ex: -i rtsp://... rtsp://...")
    parser.add_argument("-c", "--codec", default="H264", choices=["H264", "H265"],
                        help="Codec para o streaming de saída (RTSP). Padrão=H264")
    parser.add_argument("-b", "--bitrate", default=4000000, type=int,
                        help="Bitrate do encoder. Padrão=4000000 (4Mbps).")
    return parser.parse_args()


def main():
    args = parse_args()
    camera_uris = args.input
    codec = args.codec
    bitrate = args.bitrate

    number_sources = len(camera_uris)
    print("Total de fontes:", number_sources)

    # Limpa o CSV a cada execução (opcional)
    if os.path.exists("/app/logs/performance.csv"):
        os.remove("/app/logs/performance.csv")

    # Inicializa GStreamer
    Gst.init(None)

    # Cria um único pipeline
    pipeline = Gst.Pipeline.new("single-pipeline")

    # Instancia PerfData (1 entry por fonte)
    global_perf_data = PERF_DATA(num_streams=number_sources)

    # Cria nvstreammux e configura
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        print("Unable to create NvStreamMux")
        return

    streammux.set_property("width", 640)
    streammux.set_property("height", 480)
    streammux.set_property("batch-size", number_sources)
    streammux.set_property("batched-push-timeout", 33000)
    pipeline.add(streammux)

    # Para cada fonte, cria um bin e linka no streammux
    for i, uri in enumerate(camera_uris):
        print(f"[Fonte {i}] URI = {uri}")
        source_bin = create_source_bin(i, uri)
        if not source_bin:
            print("Error creating source bin")
            return
        pipeline.add(source_bin)
        sinkpad_name = f"sink_{i}"
        sinkpad = streammux.request_pad_simple(sinkpad_name)
        if not sinkpad:
            print("Unable to create sink pad in streammux")
            return
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            print("Error: source bin src pad not created")
            return
        srcpad.link(sinkpad)

    # Agora cria pgie
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        print("Unable to create pgie")
        return

    # Aponta para o arquivo de config
    pgie.set_property("config-file-path", "/app/models/new_yolo_sitelbra/yolo_sitelbra_config.txt")

    # **Força o batch-size no PGIE** para bater com o número de fontes
    pgie.set_property("batch-size", number_sources)

    # Cria tracker
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    if not tracker:
        print("Unable to create tracker")
        return

    # Exemplo de config do tracker
    config = configparser.ConfigParser()
    config.read("/app/config/dsnvanalytics_tracker_config.txt")
    for key in config["tracker"]:
        val = config.get("tracker", key)
        if key == "tracker-width":
            tracker.set_property("tracker-width", int(val))
        if key == "tracker-height":
            tracker.set_property("tracker-height", int(val))
        if key == "gpu-id":
            tracker.set_property("gpu_id", int(val))
        if key == "ll-lib-file":
            tracker.set_property("ll_lib_file", val)
        if key == "ll-config-file":
            tracker.set_property("ll_config_file", val)

    # Cria nvdsanalytics (opcional)
    nvanalytics = Gst.ElementFactory.make("nvdsanalytics", "analytics")
    if not nvanalytics:
        print("Unable to create nvanalytics")
        return
    nvanalytics.set_property("config-file", "/app/config/config_nvdsanalytics.txt")

    # Cria nvmultistreamtiler (para mosaico)
    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "tiler")
    if not tiler:
        print("Unable to create tiler")
        return

    import math
    rows = int(math.ceil(math.sqrt(number_sources)))
    columns = int(math.ceil(number_sources / rows))

    tiler.set_property("rows", rows)
    tiler.set_property("columns", columns)
    tiler.set_property("width", 1280)
    tiler.set_property("height", 720)

    # Cria nvvideoconvert
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    # Cria nvosd
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    # Cria outro videoconvert (pós-OSD)
    nvvidconv_postosd = Gst.ElementFactory.make("nvvideoconvert", "converter_postosd")
    # Cria capsfilter
    caps = Gst.ElementFactory.make("capsfilter", "filter")
    caps.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))

    # Cria encoder
    if codec == "H264":
        encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")
    else:
        encoder = Gst.ElementFactory.make("nvv4l2h265enc", "encoder")

    if not encoder:
        print("Unable to create encoder")
        return

    encoder.set_property("bitrate", bitrate)

    # Cria rtppay
    if codec == "H264":
        rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
    else:
        rtppay = Gst.ElementFactory.make("rtph265pay", "rtppay")
    rtppay.set_property("config-interval", 1)

    # Cria udpsink
    sink = Gst.ElementFactory.make("udpsink", "udpsink")
    sink.set_property("host", "224.224.255.255")
    sink.set_property("port", 5400)
    sink.set_property("async", False)
    sink.set_property("sync", True)

    # Adiciona tudo no pipeline
    for elem in [pgie, tracker, nvanalytics, tiler,
                 nvvidconv, nvosd, nvvidconv_postosd, caps,
                 encoder, rtppay, sink]:
        pipeline.add(elem)

    # Linka todos
    streammux.link(pgie)
    pgie.link(tracker)
    tracker.link(nvanalytics)
    nvanalytics.link(tiler)
    tiler.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(nvvidconv_postosd)
    nvvidconv_postosd.link(caps)
    caps.link(encoder)
    encoder.link(rtppay)
    rtppay.link(sink)

    # Instancia servidor RTSP para a saída (mosaico)
    server = GstRtspServer.RTSPServer.new()
    server.props.service = "9000"
    server.attach(None)

    factory = GstRtspServer.RTSPMediaFactory.new()
    # Ajuste a pipeline de recepção conforme a porta do udpsink (5400)
    pay_config = f'( udpsrc name=pay0 port=5400 buffer-size=524288 caps="application/x-rtp, media=video, clock-rate=90000, encoding-name=(string){codec}, payload=96" )'
    factory.set_launch(pay_config)
    factory.set_shared(True)
    mount_points = server.get_mount_points()
    mount_points.add_factory("/ds-mosaic", factory)
    print(f"\n*** DeepStream: Launched RTSP Streaming at rtsp://localhost:9000/ds-mosaic ***\n")

    # Conecta bus e loop principal
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    # Adiciona probe para atualizar FPS
    pgie_src_pad = pgie.get_static_pad("src")
    if pgie_src_pad:
        pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER,
                               pgie_src_pad_buffer_probe,
                               global_perf_data)

    # Chama callback a cada 5s
    GLib.timeout_add(5000, global_perf_data.perf_print_callback)

    # Inicia pipeline
    pipeline.set_state(Gst.State.PLAYING)
    print("Starting pipeline with multiple sources in a single pipeline.")
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)


if __name__ == "__main__":
    sys.exit(main())
