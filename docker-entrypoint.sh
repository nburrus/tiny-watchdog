#!/bin/bash

export PYTHONUNBUFFERED=1

cd /deploy

./web_server/web_server.py --urlpath "$URL_PATH" --data-dir /data |& tee -a /data/web_server.log &

# Keep launching it as it tends to throw exceptions sometimes
while true; do
    ./watchdog.py "$WATCHDOG_URL" --image-server-password "$IMAGE_SERVER_PASSWORD" --data-dir /data |& tee -a /data/watchdog.log
    sleep 1
done
