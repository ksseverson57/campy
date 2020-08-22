"""

campy Python-based simultaneous multi-camera recording script implementing real-time compression
Output is (by default) one MP4 video file for each camera

Usage: 
cd to folder where videos will be stored (separate 'CameraN' folders will be generated)
python campy.py ./campy_config.yaml

Usage example:
python C:\\Code\\campy\\campy.py D:\\20200401\\test\\videos "C:\\Users\\Wang Lab\\Documents\\Basler\\Pylon5_settings\\acA1920-150uc_1152x1024p_100fps_trigger_RGB_p6.pfs" 6 100 10

python ~/Documents/campy/campy2.py /media/kyle/Video1/20200401/test/videos /home/kyle/Documents/Basler/acA1920-150uc_1152x1024p_100fps_trigger_BGR.pfs 4 100 5

"""

# Multiprocessing Pool method sustainable up to 1 MP @ 100 Hz? (24-bit RGB)
import numpy as np
import os
import time
import sys
import threading, queue
from collections import deque
import multiprocessing as mp
from campy import CampyDefaults
from campy.cameras.basler import cam
from campy.writer import campipe
from campy.display import display
import argparse
import ast
import yaml

# TODO(FFMPEG): We can also just use any ffmpeg binary on the system path. 
if sys.platform == "linux" or sys.platform == "linux2":
    os.environ["IMAGEIO_FFMPEG_EXE"] = "/home/usr/Documents/ffmpeg/ffmpeg"
# elif sys.platform == "win32":
#     os.environ['IMAGEIO_FFMPEG_EXE'] = 'C:\\ProgramData\\FFmpeg\\bin\\ffmpeg'



def load_config(config_path):
    with open(config_path, 'rb') as f:
        config = yaml.safe_load(f)
        print(config)
    return config


def OpenMetadata(params):
    meta = {}

    # System/User Configuration metadata
    meta["FrameRate"] = params["frameRate"]
    meta["RecordingSetDuration"] = params["recTimeInSec"]
    meta["NumCameras"] = params["numCams"]

    # Camera Configuration metadata
    meta["CameraMake"] = params["cameraMake"]
    meta["PixelFormatInput"] = params["pixelFormatInput"]

    # FFmpeg Configuration metadata
    meta["PixelFormatOutput"] = params["pixelFormatOutput"]
    meta["CompressionQuality"] = params["quality"]

    # Other metadata
    # date
    # time
    # hardware?
    # os?

    return meta


def acquire_one_camera(params):
    # Initializes metadata dictionary for this camera stream
    # and inserts important configuration details
    n_cam = params['n_cam']
    meta = OpenMetadata(params)

    # Initialize queues for display window and video writer
    dispQueue = []
    # dispQueue = deque([],2)
    writeQueue = deque()

    # Open camera n_cam
    camera, meta = cam.Open(n_cam, params["camSettings"], meta)

    # Start image window display ('consumer' thread)
    if meta["CameraMake"] != "basler":
        dispQueue = deque([], 2)

        threading.Thread(
            target=display.DisplayFrames,
            daemon=True,
            args=(n_cam, dispQueue, params["displayDownsample"], meta,),
        ).start()

    # Start video writer ('consumer' thread)
    threading.Thread(
        target=campipe.WriteFrames,
        daemon=True,
        args=(n_cam, params["videoFolder"], params["gpus"], writeQueue, meta,),
    ).start()

    # Start retrieving frames (main 'producer' thread)
    cam.GrabFrames(
        n_cam,
        camera,
        meta,
        params["videoFolder"],
        writeQueue,
        dispQueue,
        params["displayFrameRate"],
        params["displayDownsample"],
    )

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
        "--cameraMake", dest="cameraMake", help="Camera make",
    )
    parser.add_argument(
        "--pixelFormatInput",
        dest="pixelFormatInput",
        help="Pixel format input.",
    )
    parser.add_argument(
        "--pixelFormatOutput",
        dest="pixelFormatOutput",
        help="Pixel format output.",
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
        help="Length of video chunks in seconds.",
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

def acquire(params):
    # Build the list of params for all cameras
    cam_params = [params for i in range(0, params['numCams'])]
    for n_cam, cam_param in enumerate(cam_params):
        cam_param['n_cam'] = n_cam

    if sys.platform == "win32":
        pool = mp.Pool(processes=params['numCams'])
        pool.map(acquire_one_camera, cam_params)

    elif sys.platform == "linux" or sys.platform == "linux2":
        ctx = mp.get_context("spawn")  # for linux compatibility
        pool = ctx.Pool(processes=params['numCams'])
        p = pool.map_async(acquire_one_camera, cam_params)
        p.get()

def main():
    parser = argparse.ArgumentParser(
        description="Campy CLI", formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.set_defaults(**CampyDefaults.__dict__)
    params = parse_clargs(parser)
    params = combine_config_and_clargs(params)
    acquire(params)