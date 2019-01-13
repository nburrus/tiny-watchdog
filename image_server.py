#!/usr/bin/env python3

import sys
import cv2
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

    i = 0
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
        
        i = i+1
        
        if i % 15 == 0:
            s.send_pyobj(in_frame)
            if debug:        
                cv2.imshow ('image', in_frame)
                cv2.waitKey (1)

    ffmpeg_process.wait()
    ffmpeg_process.terminate()

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