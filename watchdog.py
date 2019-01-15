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
    out = cv.VideoWriter(outputMp4, fourcc, 24, (width,height))
    for im in images:
        out.write(im)
    out.release()

class Archiver:    
    def __init__(self, options):
        self.options = options
        self.day_buffer_dir = os.path.join(self.options.data_dir, 'tmp_day_buffer')
        if not os.path.isdir(self.day_buffer_dir):
            os.makedirs(self.day_buffer_dir)

        self.recent_buffer_dir = os.path.join(self.options.data_dir, 'tmp_recent_buffer')
        if not os.path.isdir(self.recent_buffer_dir):
            os.makedirs(self.recent_buffer_dir)

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

    def flushDay(self, tmpDayDir, year, month, day, isPartial):
        imageFiles = sorted(glob.glob(tmpDayDir + '/*.jpg'))
        if len(imageFiles) > 0:
            outputDir = os.path.join(self.options.data_dir, 'days')
            if not os.path.isdir(outputDir):
                os.makedirs(outputDir)
            mp4Filename = None
            if isPartial:
                mp4Filename = "{:04d}-{:02d}-{:02d}_partial_{}.mp4".format(year, month, day, len(imageFiles))
            else:
                mp4Filename = "{:04d}-{:02d}-{:02d}.mp4".format(year, month, day)
                partialFiles = glob.glob(outputDir + '/{:04d}-{:02d}-{:02d}_partial*.mp4'.format(year, month, day))
                for f in partialFiles:
                    os.remove (f)
            outputMp4 = os.path.join(outputDir, mp4Filename)
            createMp4(imageFiles, outputMp4)
        if (not isPartial):
            shutil.rmtree(tmpDayDir)

    def maybeFlushPreviousDays(self, now):
        dayFolders = os.listdir(self.day_buffer_dir)
        print ('dayFolders', dayFolders)
        for dirName in dayFolders:
            fullPath = os.path.join(self.day_buffer_dir, dirName)
            if not os.path.isdir(fullPath):
                continue
            m = re.match("(\d\d\d\d)-(\d\d)-(\d\d)", dirName)
            if not m:
                continue
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            if year == now.year and month == now.month and day == now.day:
                continue 
            self.flushDay(fullPath, year, month, day, isPartial=False)

    def handleDayBuffer(self, now, image):
        imageDirName = now.strftime("%Y-%m-%d")
        imageDir = os.path.join(self.day_buffer_dir, imageDirName)

        # try to guess the previousTime from a previous run,
        if not self.previousTime and os.path.isdir(imageDir):
            self.maybeGuessPreviousTimeFromLastRun(imageDir, now)

        if self.previousTime and not isSameDay(now, self.previousTime):
            self.maybeFlushPreviousDays(now)

        minDelta = timedelta(seconds=((24*3600.)/self.options.num_images_per_day))

        if self.previousTime and (now - self.previousTime) < minDelta:
            return
            
        self.previousTime = now

        if not os.path.isdir(imageDir):
            os.makedirs(imageDir)

        imageName = now.strftime("%H_%M_%S.jpg")
        imPath = os.path.join(imageDir, imageName)
        cv.imwrite(imPath, image)
        self.flushDay(imageDir, now.year, now.month, now.day, isPartial=True)

    def handleRecentBuffer(self, now, image):
        imageName = now.strftime("%Y-%m-%d_%H_%M_%S.jpg")
        imPath = os.path.join(self.recent_buffer_dir, imageName)
        cv.imwrite(imPath, image)
        images = sorted (os.listdir(self.recent_buffer_dir))
        if (len(images) > self.options.recent_buffer_size):
            toRemove = images[0:len(images)-self.options.recent_buffer_size]
            for f in toRemove:
                os.remove(os.path.join(self.recent_buffer_dir, f))

    def processImage(self, image):
        now = datetime.now()

        # Option: simulate a super fast clock to see the behavior over days.
        # if self.fakePreviousNow:
        #     now = self.fakePreviousNow + timedelta(minutes=5)
        # self.fakePreviousNow = now

        self.handleDayBuffer (now, image)        
        self.handleRecentBuffer (now, image)

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
    parser.add_argument('--recent-buffer-size', help='Number of images to keep in the recent buffer', type=int, default=60)
    parser.add_argument('--num-images-per-day', help='Number of images in the daily summary (default is 4 per hour)', type=int, default=24*4)
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    client = WatchDog(args)
    client.reconnectToServer()
    client.readImages()
