#!/usr/bin/env python3

import sys
import cv2 as cv
import ffmpeg
import numpy as np
import zmq
import zmq.auth.thread
import time
import logging
import argparse

debug = False

def runVideoCapture(args, s):
    ffmpeg_process = (
        ffmpeg
        .input(args.video_url)
        .output('pipe:', format='rawvideo', pix_fmt='bgr24')
        .run_async(pipe_stdout=True)
    )

    minDeltaTime = 1.0
    maxWidthToSend = 640
    jpegQuality = 90
    scaleFactor = args.width / float(maxWidthToSend)
    subsampledSize = None
    if (scaleFactor > 1.5):
        subsampledSize = (int(round(args.width / scaleFactor)), int(round(args.height / scaleFactor)))

    lastImageSentTimestamp = None
    while True:
        in_bytes = ffmpeg_process.stdout.read(args.width * args.height * 3)
        if not in_bytes:
            print ("Cannot read images anymore")
            break
        in_frame = (
            np
            .frombuffer(in_bytes, np.uint8)
            .reshape([args.height, args.width, 3])
        )
        
        now = time.time()        
        if not lastImageSentTimestamp or (now-lastImageSentTimestamp) >= minDeltaTime:
            final_frame = in_frame
            if subsampledSize:
                final_frame = cv.resize(in_frame, subsampledSize)
            encode_param = [int(cv.IMWRITE_JPEG_QUALITY), jpegQuality]
            data = cv.imencode('.jpg', final_frame)[1]
            s.send_pyobj(data)
            lastImageSentTimestamp = now
            if debug:
                cv.imshow ('image', in_frame)
                cv.waitKey (1)

    ffmpeg_process.wait()

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Connects to a local RTSP stream and stream images via zmq')
    parser.add_argument('--password', help='Password to connect to the image server')
    parser.add_argument('video_url', help='RTSP URL (or video file)')
    parser.add_argument('width', type=int, help='Image width')
    parser.add_argument('height', type=int, help='Image height')
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    ctx = zmq.Context()

    if args.password:
        auth = zmq.auth.thread.ThreadAuthenticator(ctx)
        auth.start()
        auth.configure_plain(domain='*', passwords={'admin': args.password})

    s = ctx.socket(zmq.PUB)
    if args.password:
       s.plain_server = True
    s.bind("tcp://*:4242")

    # Retry to capture data every second, in case the
    # stream stopped.
    while True:
        runVideoCapture(args, s)
        time.sleep (1)
    auth.stop()