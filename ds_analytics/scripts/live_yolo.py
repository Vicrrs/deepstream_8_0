import sys, cv2
from ultralytics import YOLO

VIDEO   = sys.argv[1]
WEIGHTS = "/home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/scripts/yolo26x.pt"
DEVICE  = "cuda:0"

model = YOLO(WEIGHTS).to(DEVICE)
cap   = cv2.VideoCapture(int(VIDEO) if VIDEO.isdigit() else VIDEO)
assert cap.isOpened(), f"Não abriu {VIDEO}"

win_name = "YOLOv8 live"
cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(win_name, 960, 540)
while True:
    ret, frame = cap.read()
    if not ret:
        break

    res   = model.predict(frame, imgsz=640, conf=0.25, verbose=False)[0]
    cv2.imshow(win_name, res.plot())

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release(); cv2.destroyAllWindows()

# python live_yolo.py /home/vicrrs/Projetos/github/deepstream_7_1/streams/sitelbra02.mp4
