#!/usr/bin/env python3

import os
import re
import sys
from datetime import datetime, timedelta
import argparse
from pathlib import Path
import json
import math

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
alerts_dir = Path(args.data_dir) / 'alerts'

def parse_date(s):
    m = re.match('(\d\d\d\d)-(\d\d)-(\d\d)_(\d\d)_(\d\d)_(\d\d)', s)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2))
    day = int(m.group(3))
    hour = int(m.group(4))
    minute = int(m.group(5))
    second = int(m.group(6))
    return datetime(year, month, day, hour, minute, second)

def parse_recent_alerts():
    alerts_db = alerts_dir / 'alerts.db'
    with open(alerts_db, 'r') as f:
        f.seek(0, os.SEEK_END)
        file_pos = f.seek(max(0, f.tell() - 4096), os.SEEK_SET)
        alerts = f.readlines()
        # The first line might be cut if we did not read from file start,
        # cut it.
        if len(alerts) > 0 and file_pos > 0:
            alerts = alerts[1:]
        # Remove lines that do not finish with \n, might be because watchdog
        # is still writing to it of because we started in the middle of a line.
        alerts = filter(lambda l: l.endswith('\n'), alerts)
        print (alerts)
    
    alerts_per_day = {}
    for l in alerts:
        l = l.rstrip()
        m = re.match('(\S+) (\S+) (\{.*\})$', l)
        if not m:
            continue
        date = parse_date (m.group(1))
        event = m.group(2)
        json_content = m.group(3)
        day = date.isocalendar()
        if not day in alerts_per_day:
            alerts_per_day[day] = []
        alerts_per_day[day].append((date, event, json_content))
        print (alerts_per_day)

    days = sorted(alerts_per_day.items())
    return (days, alerts_per_day)

def compute_alerts_table_content():
    alert_days, alerts_per_day = parse_recent_alerts()
    now = datetime.now()
    today = now.isocalendar()
    yesterday = (now + timedelta(days=-1)).isocalendar()
    daily_alerts_table_content = []
    for target_day in [yesterday, today]:
        if target_day not in alerts_per_day:
            daily_alerts_table_content.append(None)
            continue
        alerts = alerts_per_day[target_day]
        num_rows = math.ceil(len(alerts) / 4)
        num_columns = 4
        content = ""
        for row in range(0, num_rows):
            content += "<tr>\n  "
            for col in range(0, num_columns):
                idx = row*num_columns + col
                if idx >= len(alerts):
                    content += "<td></td>\n"
                else:
                    alert = alerts[idx]
                    folder_name = json.loads(alert[2])['folder_name']
                    html_folder_path = Path('data') / 'alerts' / folder_name
                    video_path = html_folder_path / 'before_and_after.mp4'
                    poster_path = html_folder_path / next((alerts_dir / folder_name).glob('*_annotated.jpg')).name
                    content += f'<td><video width="320" poster="{poster_path}" onplay="slowRate(this, 0.2)" controls><source src="{video_path}" type="video/mp4">Your browser does not support the video tag.</video></td>\n'
            content += "</tr>\n"
        daily_alerts_table_content.append(content)
    return daily_alerts_table_content

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

    alerts = parse_recent_alerts()

    daily_alerts_table_content = compute_alerts_table_content()

    data = { 
        'lastImage': 'data/recent/' + lastImages[-1],
        'videosPerDay': videosPerDay,
        'daily_alerts_table_content': daily_alerts_table_content,
     }
    return flask.render_template('index.html', title='Balandro - Overview', data=data)

@app.route('/' + args.urlpath + '/data/recent/<path:path>')
def send_image(path):
    return flask.send_from_directory(recent_buffer_dir, path)

@app.route('/' + args.urlpath + '/data/alerts/<path:path>')
def send_alert_video(path):
    return flask.send_from_directory(alerts_dir, path)

@app.route('/' + args.urlpath + '/data/days/<path:path>')
def send_days_video(path):
    return flask.send_from_directory(days_dir, path)

app.run(host="0.0.0.0", port=5555)
