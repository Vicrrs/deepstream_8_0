## Dockerfile
FROM nvcr.io/nvidia/deepstream:7.1-triton-multiarch

WORKDIR /opt/nvidia/deepstream/deepstream

RUN apt-get update && apt-get install -y \
    libglib2.0-0 python3-gi python3-gst-1.0  python-gi-dev git gstreamer1.0-python3-plugin-loader \
    libgstrtspserver-1.0-0 python3.10-dev cmake g++ build-essential libglib2.0-dev gtk-doc-tools pkg-config \
    python3-pip libglib2.0-dev-bin libtool m4 autoconf automake gobject-introspection graphviz \
    libcairo2-dev libxt-dev libgirepository1.0-dev apt-utils libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    libnvinfer8 \
    && rm -rf /var/lib/apt/lists/*


RUN /opt/nvidia/deepstream/deepstream/user_deepstream_python_apps_install.sh --version 1.2.0 \
    && /opt/nvidia/deepstream/deepstream/user_additional_install.sh \
    && /opt/nvidia/deepstream/deepstream/update_rtpmanager.sh


RUN cd /opt/nvidia/deepstream/deepstream/sources/deepstream_python_apps/bindings/ && \
git submodule update --init --recursive && \
python3 3rdparty/git-partial-submodule/git-partial-submodule.py restore-sparse


RUN export GIT_SSL_NO_VERIFY=1 && cd /opt/ && git clone https://github.com/RidgeRun/gst-interpipe && cd gst-interpipe && ./autogen.sh --libdir /usr/lib/$(uname -m)-linux-gnu/ && make && make install


RUN export GST_PLUGIN_PATH=$HOME/gst-interpipe/gst/interpipe/.libs
RUN chmod 777 /dev/

ENV DISPLAY=$DISPLAY
ENV GST_PLUGIN_PATH=/opt/nvidia/deepstream/deepstream/lib/gst-plugins
ENV CUDA_MODULE_LOADING=LAZY

WORKDIR /app/
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --ignore-installed blinker -r requirements.txt

CMD ["bash"]
