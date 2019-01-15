#!/usr/bin/env python3

import os
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

app = Flask(__name__)

@app.route('/' + args.urlpath)
def hello_world():
    return 'Hello, World!'

@app.route('/' + args.urlpath + '/images/<path:path>')
def send_image(path):
    print ('path', path)
    return flask.send_from_directory(os.path.join(args.data_dir, 'tmp_recent_buffer'), path)

app.run(host="0.0.0.0", port=5555)
