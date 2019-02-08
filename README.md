# tiny-watchdog

Minimalistic tools to monitor a place with an IP camera in a private network and create a low-bandwidth website available from anywhere.

# Overview

- `image_server.py`: runs on the local network (e.g. from a netbook), connects to the IP camera via rtsp, and acts as a TCP server (ZMQ) that can send the images at a low-frequency (e.g 1/second). In addition to keeping the bandwidth much smaller, this makes it easy to access the images over a firewall by allowing a single TCP port, while rtsp is usually a pain.

- `tiny-watchdog.py`: connects to the image server, and stores the images in a local cache in a rotating way. Also creates summary videos of the day. Might get extended to do motion detection and send alerts in the future, but right now it only stores the data.

- `webserver/webserver.py`: minimalistic Flask webserver to expose the images stored by `tiny-watchdog.py`.

# Setup

- You need Python 3.x

- Install the required modules
	- For the local server: `pip install ffmpeg-python opencv-python opencv-contrib-python zmq`
	- For the public server: `pip install flask ffmpeg-python opencv-python opencv-contrib-python zmq`


# Sample usage

**On the local server** (e.g. notebook):

```
./image_server.py --bind-url 'tcp://*:4242' --password mysecretpassword "rtsp://192.168.1.20:554/onvif1" 1280 720
```

Assuming the IP camera onvif address is `192.168.1.20:554/onvif1` (this will depend on the camera model), and that the images have a size of 1280x720 pixels (720p).

This server will listen on port 4242 and send the images to anyone connecting to this port with ZMQ and the specified password.

You need to open that port to the firewall.

**On the public server**

First, run `watchdog.py` to read the images and store them.

```
./watchdog.py --image-server-password mysecretpassword 'tcp://the.image.server.com:4242'
```

The images will be stored in a `data` subfolder by default. You can change that, see the options with `--help`.

Then launch a webserver to deliver them to any browser:

```
web_server/web_server.py --urlpath mysupersecreturlpath
```

The default port for the web server is 5555. The secret url path should be hard to guess, that's the only security right now, only you should be able to guess it.

Then connect your favorite browser to [http://public.server.com:5555/mysupersecreturlpath](http://public.server.com:5555/mysupersecreturlpath) . 

You might be interested in mobile apps like [Glimpse](https://itunes.apple.com/us/app/glimpse-webpages-for-your-watch-and-notification-center/id925765624?mt=8) to keep an eye on your IP camera easily.
