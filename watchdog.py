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
        try:
            jpeg = s.recv_pyobj()
        except zmq.error.Again as e:
            sys.stderr.write ("Could not connect to the server. Check that the port is open and the password is correct.\n")
            continue
        print (len(jpeg))
        image = cv.imdecode(jpeg, cv.IMREAD_COLOR)
        print (image.shape)
        cv.imshow ('received', image)
        k = cv.waitKey(10)
        if k == ord('q'):
            break

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Connect to an image server, detect motion alarms and save alerts.')
    parser.add_argument('server_url', help='Server address and port in zmq format. Example: "tcp://myserver.com:4242"')
    parser.add_argument('--image-server-password', help='Password to connect to the image server')
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    ctx = zmq.Context()
    s = ctx.socket(zmq.SUB)
    if args.image_server_password:
        s.plain_username = b'admin'
        s.plain_password = args.image_server_password.encode('ascii')        

    s.connect(args.server_url)
    s.setsockopt(zmq.SUBSCRIBE, b'')
    s.setsockopt(zmq.RCVTIMEO, 2000)
    readImages(s)
