#!/usr/bin/env python3

import os
import re
import sys
import datetime
import argparse

import flask
from flask import Flask

def parseCommandLine():
    parser = argparse.ArgumentParser(description='Tiny webserver to access the images')
    parser.add_argument('--urlpath', help='Prefix to access the content. You can use this as security.', default="")
    parser.add_argument('--data-dir', help='Directory where images and alerts are being written to', default='data')
    return parser.parse_args()

print (sys.argv)

args = parseCommandLine()

# Make sure it's absolute path otherwise send_from_directory won't be happy.
args.data_dir = os.path.abspath(args.data_dir)

recent_buffer_dir = os.path.join(args.data_dir, 'tmp_recent_buffer')
days_dir = os.path.join(args.data_dir, 'days')

app = Flask(__name__)

# /static is delivered automatically.

@app.route('/' + args.urlpath)
@app.route('/' + args.urlpath + '/')
def index():
    lastImages = sorted(os.listdir(recent_buffer_dir))
    lastVideos_raw = sorted(os.listdir(days_dir))
    fullVideos = []
    partialVideos = []
    for video in lastVideos_raw:
        if not re.match('.*\.mp4$', video):
            continue
        if re.match('.*_partial_.*\.mp4$', video):
            partialVideos.append (video)
        else:
            fullVideos.append (video)        
    videosPerDay = fullVideos
    if len(partialVideos) > 0:
        videosPerDay.append (partialVideos[-1])
    videosPerDay = ['data/days/' + v for v in videosPerDay]

    data = { 
        'lastImage': 'data/recent/' + lastImages[-1],
        'videosPerDay': videosPerDay,
     }
    return flask.render_template('index.html', title='Balandro - Overview', data=data)

@app.route('/' + args.urlpath + '/data/recent/<path:path>')
def send_image(path):
    return flask.send_from_directory(recent_buffer_dir, path)

@app.route('/' + args.urlpath + '/data/days/<path:path>')
def send_days_video(path):
    return flask.send_from_directory(days_dir, path)

app.run(host="0.0.0.0", port=5555)
