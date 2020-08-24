"""

campy Python-based simultaneous multi-camera recording script implementing real-time compression
Output is (by default) one MP4 video file for each camera

Usage: 

campy-acquire ./configs/config.yaml

"""

import numpy as np
import os
import time
import sys
import threading, queue
from collections import deque
import multiprocessing as mp
from campy.cameras.basler import cam
from campy import CampyParams
from campy.writer import campipe
from campy.display import display
import argparse
import ast
import yaml



def load_config(config_path):
    with open(config_path, 'rb') as f:
        config = yaml.safe_load(f)
        # print(config)
    return config


def create_cam_params(params, n_cam):
    # Insert camera-specific metadata from parameters into cam_params dictionary
    cam_params = params
    cam_params["n_cam"] = n_cam
    cam_params["cameraName"] = params["cameraNames"][n_cam]
    cam_params["gpu"] = params["gpus"][n_cam]
    cam_params["baseFolder"] = os.getcwd()

    # Other metadata
    # date
    # time
    # hardware?
    # os?

    return cam_params


def acquire_one_camera(n_cam):
    # Initializes metadata dictionary for this camera stream
    # and inserts important configuration details

    # cam_params["cameraMake"] == "basler":
    #     from campy.cameras.basler import cam

    cam_params = create_cam_params(params, n_cam)

    # Open camera n_cam
    camera, cam_params = cam.Open(cam_params)

    # Initialize queues for display window and video writer
    writeQueue = deque()
    stopQueue = deque([], 1)

    # Start image window display ('consumer' thread)
    if sys.platform == 'win32' and cam_params["cameraMake"] == "basler":
        dispQueue = []
    else:
        dispQueue = deque([], 2)
        threading.Thread(
            target=display.DisplayFrames,
            daemon=True,
            args=(cam_params, dispQueue,),
        ).start()

    # Start grabbing frames ('producer' thread)
    threading.Thread(
        target = cam.GrabFrames,
        daemon=True,
        args = (cam_params,
                camera,
                writeQueue,
                dispQueue,
                stopQueue),
        ).start()

    # Start video file writer (main 'consumer' thread)
    campipe.WriteFrames(cam_params, writeQueue, stopQueue)

def parse_clargs(parser):
    parser.add_argument(
        "config", metavar="config", help="Campy configuration .yaml file.",
    )
    parser.add_argument(
        "--videoFolder", dest="videoFolder", help="Folder in which to save videos.",
    )
    parser.add_argument(
        "--camSettings", dest="camSettings", help="Path to camera settings file.",
    )
    parser.add_argument(
        "--numCams", dest="numCams", type=int, help="Number of cameras.",
    )
    parser.add_argument(
        "--frameRate", dest="frameRate", type=int, help="Frame rate.",
    )
    parser.add_argument(
        "--recTimeInSec",
        dest="recTimeInSec",
        type=int,
        help="Recording time in seconds.",
    )
    parser.add_argument(
        "--gpus",
        dest="gpus",
        type=ast.literal_eval,
        help="List of integers assigning the gpu id for each camera.",
    )
    parser.add_argument(
        "--cameraNames",
        dest="cameraNames",
        type=ast.literal_eval,
        help="List of unique camera names for each camera.",
    )
    parser.add_argument(
        "--cameraMake", dest="cameraMake", help="Camera make",
    )
    parser.add_argument(
        "--pixelFormatInput",
        dest="pixelFormatInput",
        help="Pixel format input. Use 'rgb24' for RGB or 'bayer_bggr8' for 8-bit bayer pattern.",
    )
    parser.add_argument(
        "--pixelFormatOutput",
        dest="pixelFormatOutput",
        help="Pixel format output. Use 'rgb0' for best results.",
    )
    parser.add_argument(
        "--quality",
        dest="quality",
        help="Compression quality. Lower numbers is less compression and larger files. '23' is visually lossless.",
    )
    parser.add_argument(
        "--chunkLengthInSec",
        dest="chunkLengthInSec",
        type=int,
        help="Length of video chunks in seconds for reporting recording progress.",
    )
    parser.add_argument(
        "--ffmpeg_path",
        dest="ffmpeg_path",
        help="Location of ffmpeg binary for imageio.",
    )
    parser.add_argument(
        "--displayFrameRate",
        dest="displayFrameRate",
        type=int,
        help="Display frame rate in Hz. Max ~30.",
    )
    parser.add_argument(
        "--displayDownsample",
        dest="displayDownsample",
        type=int,
        help="Downsampling factor for displaying images.",
    )
    return parser.parse_args()

def check_config(params, clargs):
    invalid_keys = []
    for key in params.keys():
        if key not in clargs.__dict__.keys():
            invalid_keys.append(key)

    if len(invalid_keys) > 0:
        invalid_key_msg = [" %s," % key for key in invalid_keys]
        msg = "Unrecognized keys in the configs: %s" % "".join(invalid_key_msg)
        raise ValueError(msg)


def combine_config_and_clargs(clargs):
    params = load_config(clargs.config)
    check_config(params, clargs)
    for param, value in clargs.__dict__.items():
        if value is not None:
            params[param] = value
    return params

def main():

    # TODO(FFMPEG): We can also just use any ffmpeg binary on the system path. 
    if params["ffmpeg_path"]:
        os.environ["IMAGEIO_FFMPEG_EXE"] = params["ffmpeg_path"]

    if sys.platform == "win32":
        pool = mp.Pool(processes=params['numCams'])
        pool.map(acquire_one_camera, range(0,params['numCams']))

    elif sys.platform == "linux" or sys.platform == "linux2":
        ctx = mp.get_context("spawn")  # for linux compatibility
        pool = ctx.Pool(processes=params['numCams'])
        p = pool.map_async(acquire_one_camera, range(0,params['numCams']))
        p.get()

parser = argparse.ArgumentParser(
        description="Campy CLI", formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
params = parse_clargs(parser)
params = combine_config_and_clargs(params)