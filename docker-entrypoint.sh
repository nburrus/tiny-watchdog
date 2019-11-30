#!/bin/bash

cd /deploy
find .
./watchdog.py "$WATCHDOG_URL" --image-server-password "$IMAGE_SERVER_PASSWORD" --data-dir /data &
./web_server/web_server.py --urlpath "$URL_PATH" --data-dir /data

