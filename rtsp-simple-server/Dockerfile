FROM debian:bookworm-slim
RUN apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl ca-certificates gstreamer-1.0 gstreamer1.0-rtsp gstreamer1.0-plugins-ugly gstreamer1.0-tools ffmpeg \
      #&& mkdir /app && cd /app && curl -L https://github.com/aler9/rtsp-simple-server/releases/download/v0.15.5/rtsp-simple-server_v0.15.5_linux_amd64.tar.gz -o rtsp-simple-server.tar.gz \
      #&& mkdir /app && cd /app && curl -L https://github.com/aler9/rtsp-simple-server/releases/download/v0.20.0/rtsp-simple-server_v0.20.0_linux_amd64.tar.gz -o rtsp-simple-server.tar.gz \
      #&& mkdir /app && cd /app && curl -L https://github.com/aler9/rtsp-simple-server/releases/download/v0.20.0/rtsp-simple-server_v0.20.0_linux_aarch64.tar.gz -o rtsp-simple-server.tar.gz \
      #&& mkdir /app && cd /app && curl -L https://github.com/aler9/mediamtx/releases/download/v0.20.0/rtsp-simple-server_v0.20.0_linux_arm64v8.tar.gz -o rtsp-simple-server.tar.gz \
      && mkdir /app && cd /app && curl -L https://github.com/bluenviron/mediamtx/releases/download/v0.23.8/mediamtx_v0.23.8_linux_amd64.tar.gz -o rtsp-simple-server.tar.gz \
      && tar -xvf rtsp-simple-server.tar.gz && rm rtsp-simple-server.tar.gz \
      && apt-get clean \
      && apt-get autoclean \
      && apt-get -y autoremove \
      && rm -rf /tmp/* /var/tmp/* \
      && rm -rf /var/lib/apt/lists/* \
      && rm -f /var/cache/apt/archives/*.deb \
      && rm -f /var/cache/apt/archives/partial/*.deb \
      && rm -f /var/cache/apt/*.bin \
      && rm -rf /root/.[acpw]*
WORKDIR /app
EXPOSE 8000
EXPOSE 8001
EXPOSE 8554
#ENTRYPOINT /app/rtsp-simple-server
