#!/usr/bin/env python3

import sys
import cv2 as cv
import numpy as np
import zmq
import zmq.auth.thread
import time
import logging
import argparse

debug = False

minDeltaTime = 1.0
maxWidthToSend = 640
jpegQuality = 90

class FFMpegCaptureSource:
    def __init__(self, args):
        self.width = args.width
        self.height = args.height
        self.video_url = args.source
        assert args.width and args.height, "You must specify --width and --height when using RTSP"
    
    def start_capture(self):
        import ffmpeg
        self.ffmpeg_process = (
            ffmpeg
            .input(self.video_url)
            .output('pipe:', format='rawvideo', pix_fmt='bgr24')
            .run_async(pipe_stdout=True)
        )

    def stop_capture(self):
        self.ffmpeg_process.wait()

    def capture_next_frame(self):
        in_bytes = self.ffmpeg_process.stdout.read(self.width * self.height * 3)
        if not in_bytes:
            print ("Cannot read images anymore")
            return None
        in_frame = (
            np
            .frombuffer(in_bytes, np.uint8)
            .reshape([self.height, self.width, 3])
        )
        return in_frame

def runVideoCapture(args, capture_source, s):    
    capture_source.start_capture()
    scaleFactor = capture_source.width / float(maxWidthToSend)
    subsampledSize = None
    if (scaleFactor > 1.5):
        subsampledSize = (int(round(capture_source.width / scaleFactor)), int(round(capture_source.height / scaleFactor)))

    lastImageSentTimestamp = None
    while True:
        in_frame = capture_source.capture_next_frame()
        if in_frame is None:
            print ("Cannot read images anymore")
            break
        
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

    capture_source.stop_capture()    

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Connects to a local RTSP stream and stream images via zmq')
    parser.add_argument('source', help='picamera, RTSP URL or video file')
    parser.add_argument('--password', help='Password to connect to the image server')
    parser.add_argument('--width', type=int, help='Image width, required if RTSP URL')
    parser.add_argument('--height', type=int, help='Image height, required if RTSP URL')
    parser.add_argument('--bind-url', help='ZMQ bind URL. Default is "tcp://*:4242"', default='tcp://*:4242')
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
    s.bind(args.bind_url)

    capture_source = None
    if args.source == 'picamera':
        capture_source = None
    else:
        capture_source = FFMpegCaptureSource(args)

    # Retry to capture data every second, in case the
    # stream stopped.
    while True:
        runVideoCapture(args, capture_source, s)
        time.sleep (1)
    auth.stop()