#!/bin/bash

export PYTHONUNBUFFERED=1

cd /deploy
./watchdog.py "$WATCHDOG_URL" --image-server-password "$IMAGE_SERVER_PASSWORD" --data-dir /data |& tee /data/watchdog.log &
./web_server/web_server.py --urlpath "$URL_PATH" --data-dir /data |& tee /data/web_server.log
