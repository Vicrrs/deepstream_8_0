# ds_analytics/pipeline/nodes.py
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

def create_source_bin(index: int, uri: str):
    bin_name = f"source-bin-{index:02d}"
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        raise RuntimeError("Unable to create source bin")

    def _cb_newpad(decodebin, decoder_src_pad, data):
        caps = decoder_src_pad.get_current_caps()
        gststruct = caps.get_structure(0)
        name = gststruct.get_name()
        features = caps.get_features(0)
        if "video" in name and features.contains("memory:NVMM"):
            ghost = data.get_static_pad("src")
            if not ghost.set_target(decoder_src_pad):
                print("Failed to link decoder src to ghost pad")

    def _child_added(child_proxy, obj, name, user_data):
        # Force RTSP over TCP to avoid UDP packet loss/reconnect storms.
        if "source" in name:
            try:
                if obj.find_property("protocols") is not None:
                    obj.set_property("protocols", 4)  # GST_RTSP_LOWER_TRANS_TCP
                if obj.find_property("latency") is not None:
                    obj.set_property("latency", 300)
                if obj.find_property("drop-on-latency") is not None:
                    obj.set_property("drop-on-latency", True)
            except Exception:
                pass
        if "decodebin" in name:
            obj.connect("child-added", _child_added, user_data)

    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", f"uri-decode-bin-{index}")
    if not uri_decode_bin:
        raise RuntimeError("Unable to create uridecodebin")
    uri_decode_bin.set_property("uri", uri)
    uri_decode_bin.connect("pad-added", _cb_newpad, nbin)
    uri_decode_bin.connect("child-added", _child_added, nbin)

    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC)
    nbin.add_pad(bin_pad)
    return nbin

def make(name, factory):
    elem = Gst.ElementFactory.make(factory, name)
    if not elem:
        raise RuntimeError(f"Unable to create element {factory}")
    return elem

def link_many(*elems):
    for a, b in zip(elems, elems[1:]):
        if not a.link(b):
            raise RuntimeError(f"Failed to link {a.name} -> {b.name}")
