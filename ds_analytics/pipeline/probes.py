# /app/pipeline/probes.py
import ctypes
import numpy as np
import pyds
from gi.repository import Gst

CROP_SCORE_THRESH = 0.10
MAX_DETECTIONS_PER_FRAME = 100

def _get_tensor_as_numpy(tensor_meta: pyds.NvDsInferTensorMeta, layer_name: str):
    for i in range(tensor_meta.num_output_layers):
        layer = pyds.get_nvds_LayerInfo(tensor_meta, i)
        if layer.layerName != layer_name:
            continue

        dims = layer.inferDims
        shape = [dims.d[j] for j in range(dims.numDims)]
        n = int(np.prod(shape))

        ptr = ctypes.cast(pyds.get_ptr(layer.buffer), ctypes.POINTER(ctypes.c_float))
        arr = np.ctypeslib.as_array(ptr, shape=(n,)).copy()
        return arr.reshape(shape)
    return None


def _frame_dims(buf, fmeta):
    h = float(getattr(fmeta, "source_frame_height", 0) or 0)
    w = float(getattr(fmeta, "source_frame_width", 0) or 0)
    if h > 0 and w > 0:
        return h, w
    try:
        frame = pyds.get_nvds_buf_surface(hash(buf), fmeta.batch_id)
        img = np.array(frame, copy=False, order="C")
        if img is not None and img.size > 0:
            h, w = img.shape[:2]
            if h > 0 and w > 0:
                return float(h), float(w)
    except Exception:
        pass
    return 720.0, 1280.0

def pgie_src_pad_buffer_probe(pad, info, perf_mgr):
    buf = info.get_buffer()
    if not buf:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(buf))
    l_frame = batch_meta.frame_meta_list
    counts_by_stream = {}
    counts_total = perf_mgr._init_counts()

    while l_frame:
        try:
            fmeta = pyds.NvDsFrameMeta.cast(l_frame.data)
            perf_mgr.on_frame(fmeta.pad_index)

            stream_key = perf_mgr.stream_key(fmeta.pad_index)
            tensor_meta = None

            # pega tensor_meta (se output_tensor_meta=true)
            l_user = fmeta.frame_user_meta_list
            while l_user:
                umeta = pyds.NvDsUserMeta.cast(l_user.data)
                if umeta.base_meta.meta_type == pyds.NvDsMetaType.NVDSINFER_TENSOR_OUTPUT_META:
                    tensor_meta = pyds.NvDsInferTensorMeta.cast(umeta.user_meta_data)
                    break
                l_user = l_user.next

            # Se não houve obj_meta (Triton sem postprocess), tenta decodificar tensor
            if fmeta.obj_meta_list is None and tensor_meta is not None:
                out = _get_tensor_as_numpy(tensor_meta, "output")
                if out is None:
                    out = _get_tensor_as_numpy(tensor_meta, "output0")
                if out is not None:
                    arr = np.array(out)
                    if arr.ndim == 3 and arr.shape[0] == 1:
                        arr = arr[0]
                    if arr.ndim == 2 and arr.shape[0] == 6 and arr.shape[1] != 6:
                        arr = arr.T
                    if arr.ndim == 2 and arr.shape[1] >= 6:
                        h, w = _frame_dims(buf, fmeta)
                        dets = 0
                        for row in arr:
                            x1, y1, x2, y2, score, cls_id = row[:6]
                            if score < CROP_SCORE_THRESH:
                                continue
                            # normalize or xywh support
                            if x2 <= 1.5 and y2 <= 1.5:
                                x1 *= w
                                x2 *= w
                                y1 *= h
                                y2 *= h
                            if x2 <= x1 or y2 <= y1:
                                # treat as cx,cy,w,h
                                cx, cy, bw, bh = x1, y1, x2, y2
                                x1 = cx - bw / 2.0
                                y1 = cy - bh / 2.0
                                x2 = cx + bw / 2.0
                                y2 = cy + bh / 2.0
                            x1 = max(0.0, min(w - 1.0, x1))
                            y1 = max(0.0, min(h - 1.0, y1))
                            x2 = max(0.0, min(w - 1.0, x2))
                            y2 = max(0.0, min(h - 1.0, y2))
                            if x2 <= x1 or y2 <= y1:
                                continue
                            obj_meta = pyds.nvds_acquire_obj_meta_from_pool(batch_meta)
                            obj_meta.class_id = int(cls_id)
                            obj_meta.confidence = float(score)
                            obj_meta.rect_params.left = float(x1)
                            obj_meta.rect_params.top = float(y1)
                            obj_meta.rect_params.width = float(x2 - x1)
                            obj_meta.rect_params.height = float(y2 - y1)
                            label = perf_mgr.label_for_class_id(int(cls_id))
                            try:
                                obj_meta.obj_label = label
                            except Exception:
                                pass
                            pyds.nvds_add_obj_meta_to_frame(fmeta, obj_meta, None)
                            dets += 1
                            if dets >= MAX_DETECTIONS_PER_FRAME:
                                break

            frame_counts = perf_mgr._init_counts()
            l_obj = fmeta.obj_meta_list
            while l_obj:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration:
                    break
                label = None
                try:
                    if obj_meta.obj_label:
                        raw = obj_meta.obj_label
                        if isinstance(raw, bytes):
                            label = raw.decode("utf-8", errors="ignore")
                        else:
                            label = str(raw)
                except Exception:
                    label = None
                if not label:
                    label = perf_mgr.label_for_class_id(int(obj_meta.class_id))
                frame_counts[label] = frame_counts.get(label, 0) + 1
                counts_total[label] = counts_total.get(label, 0) + 1
                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break
            counts_by_stream[stream_key] = frame_counts

            l_frame = l_frame.next
        except StopIteration:
            break

    perf_mgr.update_counts(counts_by_stream, counts_total)

    return Gst.PadProbeReturn.OK
