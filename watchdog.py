#!/usr/bin/env python3

import sys
import cv2 as cv
import numpy as np
import zmq
import time
import logging
import argparse

class WatchDog:
    def __init__(self, options):
        self.zmqCtx = zmq.Context()
        self.options = options

    def reconnectToServer(self):
        print ("Reconnecting to the server...")
        self.zmqSocket = self.zmqCtx.socket(zmq.SUB)
        if self.options.image_server_password:
            self.zmqSocket.plain_username = b'admin'
            self.zmqSocket.plain_password = self.options.image_server_password.encode('ascii')
        self.zmqSocket.connect(self.options.server_url)
        self.zmqSocket.setsockopt(zmq.SUBSCRIBE, b'')
        self.zmqSocket.setsockopt(zmq.RCVTIMEO, 5000)
        self.numReceiveFailures = 0

    def readImages(self):
        while True:
            try:
                jpeg = self.zmqSocket.recv_pyobj()
            except zmq.error.Again as e:
                sys.stderr.write ("Could not communicate with the server. Check that the port is open and the password is correct.\n")
                self.numReceiveFailures += 1
                if self.numReceiveFailures > 3:
                    self.reconnectToServer()
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
    parser.add_argument('--images-dir', help='Directory ')
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    client = WatchDog(args)
    client.reconnectToServer()
    client.readImages()
