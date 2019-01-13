#!/usr/bin/env python3

import sys
import cv2 as cv
import numpy as np
import zmq
import time
import logging
import argparse

def readImages(s):
    while True:
        jpeg = s.recv_pyobj()
        print (len(jpeg))
        image = cv.imdecode(jpeg, cv.IMREAD_COLOR)
        print (image.shape)
        cv.imshow ('received', image)
        cv.waitKey(10)

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Connect to an image server, detect motion alarms and save alerts.')
    parser.add_argument('--image-server-password', help='Password to connect to the image server')
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    ctx = zmq.Context()
    s = ctx.socket(zmq.SUB)
    if args.image_server_password:
        s.plain_username = b'admin'
        s.plain_password = args.image_server_password.encode('ascii')        

    s.connect("tcp://127.0.0.1:4242")
    s.setsockopt(zmq.SUBSCRIBE, b'')
    readImages(s)
