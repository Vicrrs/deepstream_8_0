from ultralytics import YOLO

model = YOLO("/home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/scripts/yolo26n.pt")
model.export(format="onnx", opset=17, simplify=True, dynamic=False)  # gera yolo26n.onnx
