import sys, cv2
from ultralytics import YOLO

VIDEO   = sys.argv[1]
WEIGHTS = "/home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/scripts/yolo26x.pt"
DEVICE  = "cuda:0"

model = YOLO(WEIGHTS).to(DEVICE)

names = model.names
if isinstance(names, dict):
    person_ids = [i for i, n in names.items() if str(n).lower() in ("person", "pessoa")]
else:
    person_ids = [i for i, n in enumerate(names) if str(n).lower() in ("person", "pessoa")]

PERSON_CLASS_ID = person_ids[0] if person_ids else 0

cap = cv2.VideoCapture(int(VIDEO) if VIDEO.isdigit() else VIDEO)
assert cap.isOpened(), f"Nao abriu {VIDEO}"

win_name = "YOLO26 - Pessoas"
cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(win_name, 960, 540)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    res = model.predict(
        frame,
        imgsz=640,
        conf=0.40,
        classes=[PERSON_CLASS_ID],
        verbose=False,
        device=DEVICE
    )[0]

    cv2.imshow(win_name, res.plot())

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
