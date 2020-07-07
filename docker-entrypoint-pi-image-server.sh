#!/bin/bash

export PYTHONUNBUFFERED=1

cd /deploy
./image_server.py --password "$IMAGE_SERVER_PASSWORD" picamera 640 480 |& tee /data/image_server.log
