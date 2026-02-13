#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import sys
import os
from ultralytics import YOLO

def main():
    if len(sys.argv) < 3:
        print("\nUso: python deteccao_realtime.py <modelo.pt> <video.mp4>\n")
        print("Exemplo: python deteccao_realtime.py epi_best.pt video_teste.mp4\n")
        sys.exit(1)

    model_path = sys.argv[1]
    video_path = sys.argv[2]

    if not os.path.exists(model_path):
        sys.exit(f"Modelo nao encontrado: {model_path}")

    if not os.path.exists(video_path):
        sys.exit(f"Video nao encontrado: {video_path}")

    print(f"Carregando modelo: {model_path}")
    model = YOLO(model_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        sys.exit(f"Erro ao abrir video: {video_path}")

    print(f"Exibindo video: {video_path}")
    print("Pressione ESC para sair.")

    window_width = 1280
    window_height = 720
    window_name = "YOLO - Deteccao em Tempo Real"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, window_width, window_height)

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Fim do video.")
            break

        results = model.predict(frame, verbose=False)
        annotated_frame = results[0].plot()

        frame_resized = cv2.resize(annotated_frame, (window_width, window_height))

        cv2.imshow(window_name, frame_resized)

        if cv2.waitKey(1) & 0xFF == 27:
            print("Encerrado pelo usuario.")
            break

        frame_count += 1
        if frame_count % 30 == 0:
            print(f"{frame_count} frames processados...")

    cap.release()
    cv2.destroyAllWindows()
    print("\nDetecção finalizada com sucesso!")


if __name__ == "__main__":
    main()


    
    

""" 
Drone Frente EPI:
python general.py /home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/models/EPI/best.pt /home/vicrrs/Projetos/github/deepstream_7_1/streams/sitelbra03.MP4

Drone Perfil EPI:
python general.py /home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/models/EPI_perfil/EPI_container_final_best.pt /media/ssd_dados/SITELBRA/epi/epi01.MP4

HALL:
python general.py /home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/models/Hall/HALL_people_best.pt /home/vicrrs/Projetos/github/deepstream_7_1/streams/sitelbra02.mp4

Entrada:
python general.py  /home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/models/person/best.pt /home/vicrrs/Projetos/github/deepstream_7_1/streams/sitelbra01.mp4

Carro:
python general.py /home/vicrrs/Projetos/github/deepstream_7_1/ds_analytics/models/rodovia/CAR_best_final.pt /media/ssd_dados/SITELBRA/videos_anotacao/carros3.mp4

"""
