FROM python:3-slim-buster

# Opencv-python needs a few libraries.
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev

RUN pip install opencv-python opencv-contrib-python flask imageio zmq ffmpeg

COPY watchdog.py /deploy/
COPY image_server.py /deploy/
COPY web_server /deploy/web_server
COPY docker-entrypoint.sh /deploy/entrypoint.sh

ENV WATCHDOG_URL tcp://myserver.com:4242
ENV IMAGE_SERVER_PASSWORD mypassword
ENV URL_PATH mysecreturlpath

EXPOSE 5555
VOLUME ["/data"]

ENTRYPOINT ["/deploy/entrypoint.sh"]
