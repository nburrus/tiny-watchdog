#!/usr/bin/env python3

import sys
import cv2 as cv
import numpy as np
import zmq
import time
from datetime import datetime, timedelta
import logging
import argparse
import os
import glob
import re
import imageio
import shutil

#  tmp_motion_alert_buffer/
#    1 image per second over the past 30 seconds
#    transformed into gif once motion alert confirmed
#  tmp_day_buffer/
#  alerts/
#     date_alert.gif
#  days/
#     date.mp4

def isSameDay(time1, time2):
    return (time1.year == time2.year
            and time1.month == time2.month
            and time1.day == time2.day)

def isSameHour(time1, time2):
    return isSameDay(time1, time2) and (time1.hour == time2.hour)

def createMp4(filenames, outputMp4):
    images = [cv.imread(f) for f in filenames]
    height, width = images[0].shape[0:2]
    fourcc = cv.VideoWriter_fourcc(*'H264')
    out = cv.VideoWriter(outputMp4, fourcc, 12, (width,height))
    for im in images:
        out.write(im)
    out.release()

class Archiver:    
    def __init__(self, options):
        self.options = options
        self.day_buffer_dir = os.path.join(self.options.data_dir, 'tmp_day_buffer')
        if not os.path.isdir(self.day_buffer_dir):
            os.makedirs(self.day_buffer_dir)
        self.previousTime = None
        self.fakePreviousNow = None

    def maybeGuessPreviousTimeFromLastRun(self, imageDir, now):
        files = sorted(glob.glob(imageDir + '/*.jpg'))
        if len(files) > 0:
            mostRecent = os.path.basename(files[-1])
            print (mostRecent)
            m = re.match("(\d\d)_(\d\d)_(\d\d).jpg", mostRecent)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2))
                second = int(m.group(3))
                self.previousTime = now.replace(hour=hour, minute=minute, second=second)
                print ("[Debug] previous time was ", self.previousTime)

    def flushDay(self, tmpDayDir, year, month, day):
        imageFiles = sorted(glob.glob(tmpDayDir + '/*.jpg'))
        if len(imageFiles) > 0:
            outputDir = os.path.join(self.options.data_dir, 'days')
            if not os.path.isdir(outputDir):
                os.makedirs(outputDir)
            mp4Filename = "{:04d}_{:02d}_{:02d}.mp4".format(year, month, day)
            outputMp4 = os.path.join(outputDir, mp4Filename)
            createMp4(imageFiles, outputMp4)
        shutil.rmtree(tmpDayDir)

    def maybeFlushPreviousDays(self, now):
        dayFolders = os.listdir(self.day_buffer_dir)
        print ('dayFolders', dayFolders)
        for dirName in dayFolders:
            fullPath = os.path.join(self.day_buffer_dir, dirName)
            if not os.path.isdir(fullPath):
                continue
            m = re.match("(\d\d\d\d)_(\d\d)_(\d\d)", dirName)
            if not m:
                continue
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            if year == now.year and month == now.month and day == now.day:
                continue 
            self.flushDay(fullPath, year, month, day)

    def processImage(self, image):
        now = datetime.now()
        # Option: simulate a super fast clock to see the behavior over days.
        # if self.fakePreviousNow:
        #     now = self.fakePreviousNow + timedelta(minutes=240+30)
        # self.fakePreviousNow = now

        imageDirName = now.strftime("%Y_%m_%d")
        imageDir = os.path.join(self.day_buffer_dir, imageDirName)

        # try to guess the previousTime from a previous run,
        if not self.previousTime and os.path.isdir(imageDir):
            self.maybeGuessPreviousTimeFromLastRun(imageDir, now)

        if self.previousTime and not isSameDay(now, self.previousTime):
            self.maybeFlushPreviousDays(now)

        if self.previousTime and isSameHour(now, self.previousTime):
            return
            
        self.previousTime = now

        if not os.path.isdir(imageDir):
            os.makedirs(imageDir)

        imageName = now.strftime("%H_%M_%S.jpg")
        imPath = os.path.join(imageDir, imageName)
        cv.imwrite(imPath, image)
        print ("[Debug] Wrote ", imPath)

class WatchDog:
    def __init__(self, options):
        self.archiver = Archiver(options)
        self.zmqCtx = zmq.Context()
        self.options = options
        if not os.path.isdir(self.options.data_dir):
            print ("Creating {} to store images and alerts".format(self.options.data_dir))
            os.makedirs(self.options.data_dir)

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
            # print (len(jpeg))
            image = cv.imdecode(jpeg, cv.IMREAD_COLOR)
            # print (image.shape)
            self.archiver.processImage (image)
            cv.imshow ('received', image)
            k = cv.waitKey(10)
            if k == ord('q'):
                break

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Connect to an image server, detect motion alarms and save alerts.')
    parser.add_argument('server_url', help='Server address and port in zmq format. Example: "tcp://myserver.com:4242"')
    parser.add_argument('--image-server-password', help='Password to connect to the image server')
    parser.add_argument('--data-dir', help='Directory used to save images and alerts', default='data')
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    client = WatchDog(args)
    client.reconnectToServer()
    client.readImages()
