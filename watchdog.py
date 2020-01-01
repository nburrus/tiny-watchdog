#!/usr/bin/env python3

import sys
import time
from datetime import datetime, timedelta
import logging
import argparse
import os
import glob
import re
import shutil
from pathlib import Path
from collections import namedtuple

import imageio
import ffmpeg
import cv2 as cv
import numpy as np
import zmq

import motion_detector

debug = False

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

    ffmpeg_process = (
        ffmpeg
        .input('pipe:', format='rawvideo', pix_fmt='bgr24', s='{}x{}'.format(width, height))
        .output(outputMp4, pix_fmt='yuv420p', vcodec='libx264')
        .run_async(pipe_stdin=True)
    )
    for image in images:
        print ('image.shape', image.shape)
        ffmpeg_process.stdin.write(
            image
            .astype(np.uint8)
            .tobytes()
        )
    ffmpeg_process.stdin.close()
    ffmpeg_process.wait()
    print ("{} written".format(outputMp4))

class Archiver:    
    def __init__(self, options):
        self.options = options
        self.day_buffer_dir = os.path.join(self.options.data_dir, 'tmp_day_buffer')
        if not os.path.isdir(self.day_buffer_dir):
            os.makedirs(self.day_buffer_dir)

        self.recent_buffer_dir = os.path.join(self.options.data_dir, 'tmp_recent_buffer')
        if not os.path.isdir(self.recent_buffer_dir):
            os.makedirs(self.recent_buffer_dir)

        self.alerts_dir = os.path.join(self.options.data_dir, 'alerts')
        if not os.path.isdir(self.alerts_dir):
            os.makedirs(self.alerts_dir)

        self.alert_db = str(Path(self.alerts_dir) / 'alerts.db')
        open(self.alert_db, 'a') # make sure it gets created

        self.previousTime = None
        self.fakePreviousNow = None
        self.activeAlerts = []

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
                mp4Filename = "{:04d}-{:02d}-{:02d}_partial_{:03d}.mp4".format(year, month, day, len(imageFiles))
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

    def handleCurrentAlert(self, now, image):
        alerts_to_remove = []
        for alert in self.activeAlerts:
            if (now-alert.start_time).seconds > self.options.seconds_to_record_after_alert:
                alerts_to_remove.append(alert)
                continue
            imageName = now.strftime("%Y-%m-%d_%H_%M_%S.jpg")            
            cv.imwrite(str(alert.folder_path / imageName), image)
        
        for a in alerts_to_remove:
            self.finalizeAlert (a)

    def finalizeAlert(self, alert):
        print (f"Alert {alert.folder_name} is finished, generating the mp4")        
        recorded_files = sorted(alert.folder_path.glob('*.jpg'))
        recorded_files = [str(f) for f in recorded_files]
        outputMp4 = str(alert.folder_path / 'before_and_after.mp4')
        createMp4(recorded_files, outputMp4)
        for f in recorded_files:
            if not '_annotated.jpg' in f:
                os.remove(f)
        self.activeAlerts.remove(alert)

    def recordNewAlert(self, r: motion_detector.Results):
        event_name = r.event.name
        now = datetime.now()
        formatted_now = now.strftime(f"%Y-%m-%d_%H_%M_%S")
        folder_name = f"{formatted_now}_{event_name}"
        folder_path = Path(self.alerts_dir) / folder_name
        os.makedirs(folder_path)
        print ("Recording new alert into ", folder_name)

        images = sorted (os.listdir(self.recent_buffer_dir))
        for im in images:
            shutil.copy(os.path.join(self.recent_buffer_dir, im), folder_path / im)

        # Save the annotated image.
        annotated_image_name = f"{formatted_now}_{event_name}_annotated.jpg"
        cv.imwrite(str(folder_path / annotated_image_name), r.annotated_image)

        Alert = namedtuple('Alert', 'start_time folder_name folder_path')
        active_alert = Alert(start_time = now, folder_name=folder_name, folder_path=folder_path)
        with open(self.alert_db, 'a') as f:
            json_str = f"{{'folder_name': '{folder_name}'}}"
            f.write(f"{formatted_now} {event_name} {json_str}\n")
        self.activeAlerts.append (active_alert)

    def processImage(self, image):
        now = datetime.now()

        # Option: simulate a super fast clock to see the behavior over days.
        # if self.fakePreviousNow:
        #     now = self.fakePreviousNow + timedelta(minutes=5)
        # self.fakePreviousNow = now

        self.handleDayBuffer (now, image)        
        self.handleRecentBuffer (now, image)
        self.handleCurrentAlert (now, image)

class WatchDog:
    def __init__(self, options):
        self.archiver = Archiver(options)
        self.motionDetector = motion_detector.Detector()
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
            if debug:
                cv.imshow ('received', image)
            self.archiver.processImage (image)
            e = self.motionDetector.processImage (image)
            if e.event != motion_detector.Event.NONE:
                self.archiver.recordNewAlert (e)

            k = cv.waitKey(10)
            if k == ord('q'):
                break

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Connect to an image server, detect motion alarms and save alerts.')
    parser.add_argument('server_url', help='Server address and port in zmq format. Example: "tcp://myserver.com:4242"')
    parser.add_argument('--image-server-password', help='Password to connect to the image server')
    parser.add_argument('--data-dir', help='Directory used to save images and alerts', default='data')
    parser.add_argument('--recent-buffer-size', help='Number of images to keep in the recent buffer', type=int, default=30)
    parser.add_argument('--num-images-per-day', help='Number of images in the daily summary (default is 4 per hour)', type=int, default=24*4)
    parser.add_argument('--seconds-to-record-after-alert', help="Number of seconds to record after an alert.", default=10)
    return parser.parse_args()

if __name__ == "__main__":
    args = parseCommandLine()

    client = WatchDog(args)
    client.reconnectToServer()
    client.readImages()
