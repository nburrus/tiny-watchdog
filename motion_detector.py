#!/usr/bin/env python3

import sys
import time
from datetime import datetime, timedelta
from collections import namedtuple
from enum import Enum

import cv2 as cv
import numpy as np

debug = True

class Event(Enum):
    NONE = 0
    MOTION_DETECTED = 1

Results = namedtuple('Results', 'event annotated_image')
no_event = Results(event=Event.NONE, annotated_image=None)

class Options:
    def __init__(self):
        self.num_images_to_initialize = 120
        self.min_seconds_between_detections = 120

class Detector:
    def __init__(self, options=Options()):
        self.options = options
        # self.fgbg = cv.bgsegm.createBackgroundSubtractorMOG()
        # self.fgbg = cv.bgsegm.createBackgroundSubtractorGMG()
        self.fgbg = cv.bgsegm.createBackgroundSubtractorCNT()
        #self.fgbg = cv.bgsegm.createBackgroundSubtractorMOG()
        self.kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE,(3,3))
        self.num_images_processed = 0
        self.last_detection_date = None

    def processImage(self, image):
        self.num_images_processed += 1
        fgmask = self.fgbg.apply(image)
        fgmask = cv.morphologyEx(fgmask, cv.MORPH_OPEN, self.kernel)

        contours, hierarchy = cv.findContours(fgmask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        large_contours = []
        for c in contours:
            if cv.contourArea(c) > 100:
                large_contours.append(c)

        annotated_image = cv.drawContours(image, large_contours, -1, (255,0,0), 3)

        if debug:
            cv.imshow('mask', fgmask)
            cv.imshow('annotated_detections', annotated_image)

        if len(large_contours) == 0:
            return no_event

        print (f"Raw motion detected ({len(contours)} contours), let's see if it triggers an event")

        # Let the detector enough time to initialize.
        if self.num_images_processed < self.options.num_images_to_initialize:
            return no_event

        # Already triggered an event less than a minute ago, don't do it again.
        if self.last_detection_date != None:
            seconds_since_last_detection = (datetime.now()-self.last_detection_date).seconds
            if seconds_since_last_detection < self.options.min_seconds_between_detections:
                return no_event

        self.last_detection_date = datetime.now()
        return Results(event=Event.MOTION_DETECTED, annotated_image=annotated_image)

if __name__ == '__main__':
    detector = Detector()
    cap = cv.VideoCapture('scene1.mp4')
    assert (cap.isOpened() == True)
    
    while cap.isOpened():
        # Capture frame-by-frame
        ret, frame = cap.read()
        if ret == False:
            break

        # Display the resulting frame
        cv.imshow('Frame',frame)
    
        event = detector.processImage(frame)
        print (event)

        # Press Q on keyboard to  exit
        if cv.waitKey(0) & 0xFF == ord('q'):
            break

    cap.release()
    cv.destroyAllWindows()
