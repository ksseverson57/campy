"""
CamPy Python-based multi-camera recording software.
Integrates machine vision camera API with ffmpeg real-time compression
Outputs are one MP4 video file for each camera and metadata files

'campy' is the main console. 
User inputs are loaded from config yaml file using a command line interface (CLI) into the 'params' object.
Params are then assigned to each camera in the 'cam_params' object.
	* Camera loading index and order is set by 'cameraSelection'.
	* If string, this param is applied to all cameras.
	* If list of strings, params are assigned to each camera, using the order in cameraSelection.
Camera streams are acquired and encoded in parallel using multiprocessing.

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
from campy import CampyParams
from campy.writer import campipe
from campy.display import display
import argparse
import ast
import yaml


def LoadConfig(config_path):
	with open(config_path, 'rb') as f:
		config = yaml.safe_load(f)
	return config

def OptParams(params, cam_params, opt_params_list):
	# Optionally, user provides a single string or a list of strings, equal in size to numCams
	# String is passed to all cameras. Else, each list item is passed to its respective camera
	n_cam = cam_params["n_cam"]
	for i in range(len(opt_params_list)):
		if type(params[opt_params_list[i]]) is list:
			if len(params[opt_params_list[i]]) == params["numCams"]:
				cam_params[opt_params_list[i]] = params[opt_params_list[i]][n_cam]
			else: print('{} list is not the same size as numCams.'.format(opt_params_list[i]))
	return cam_params

def CreateCamParams(params, n_cam):
	# Insert camera-specific metadata from parameters into cam_params dictionary
	cam_params = params
	cam_params["n_cam"] = n_cam
	cam_params["cameraName"] = params["cameraNames"][n_cam]
	cam_params["baseFolder"] = os.getcwd()
	opt_params_list = ["frameRate", "cameraSelection", "cameraSettings", "cameraMake", 
						"pixelFormatInput", "pixelFormatOutput", "frameWidth", "frameHeight",
						"ffmpegLogLevel", "gpuID", "gpuMake", "codec", "quality",
						"chunkLengthInSec", "displayFrameRate", "displayDownsample"]
	cam_params = OptParams(params, cam_params, opt_params_list)
	return cam_params

def AcquireOneCamera(n_cam):
	# Initializes metadata dictionary for this camera stream
	# and inserts important configuration details

	# Load camera parameters from config
	cam_params = CreateCamParams(params, n_cam)

	# Import the correct camera module for your camera
	if cam_params["cameraMake"] == "basler":
		from campy.cameras.basler import cam
	elif cam_params["cameraMake"] == "flir":
		from campy.cameras.flir import cam

	# Open camera n_cam
	camera, cam_params = cam.OpenCamera(cam_params)

	# Initialize queues for video writer
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

def ParseClargs(parser):
	parser.add_argument(
		"config", metavar="config", help="Campy configuration .yaml file.",
	)
	parser.add_argument(
		"--videoFolder", 
		dest="videoFolder", 
		help="Folder in which to save videos.",
	)
	parser.add_argument(
		"--videoFilename", 
		dest="videoFilename", 
		help="Name for video output file.",
	)
	parser.add_argument(
		"--frameRate", 
		dest="frameRate",
		type=ast.literal_eval, 
		help="Frame rate equal to trigger frequency.",
	)
	parser.add_argument(
		"--recTimeInSec",
		dest="recTimeInSec",
		type=int,
		help="Recording time in seconds.",
	)    
	parser.add_argument(
		"--emulate", 
		dest="emulate", 
		type=bool, 
		help="Toggle for emulation mode (decode video file for debug/development).",
	)
	parser.add_argument(
		"--numCams", 
		dest="numCams", 
		type=int, 
		help="Number of cameras.",
	)
	parser.add_argument(
		"--cameraNames", 
		dest="cameraNames", 
		type=ast.literal_eval, 
		help="Names assigned to the cameras in the order of cameraSelection.",
	)
	parser.add_argument(
		"--cameraSelection",
		dest="cameraSelection",
		type=ast.literal_eval,
		help="Selects and orders camera indices to include in the recording. List length must be equal to numCams",
	)
	parser.add_argument(
		"--cameraSettings", 
		dest="cameraSettings",
		type=ast.literal_eval, 
		help="Path to camera settings file.",
	)
	parser.add_argument(
		"--frameHeight", 
		dest="frameHeight",
		type=ast.literal_eval, 
		help="Frame height in pixels.",
	)
	parser.add_argument(
		"--frameWidth", 
		dest="frameWidth",
		type=ast.literal_eval, 
		help="Frame width in pixels.",
	)
	parser.add_argument(
		"--cameraMake", 
		dest="cameraMake", 
		type=ast.literal_eval,
		help="Company that produced the camera. Currently supported: 'basler'.",
	)
	parser.add_argument(
		"--pixelFormatInput",
		dest="pixelFormatInput",
		type=ast.literal_eval,
		help="Pixel format input. Use 'rgb24' for RGB or 'bayer_bggr8' for 8-bit bayer pattern.",
	)
	parser.add_argument(
		"--pixelFormatOutput",
		dest="pixelFormatOutput",
		type=ast.literal_eval,
		help="Pixel format output. Use 'rgb0' for best results.",
	)
	parser.add_argument(
		"--ffmpegPath",
		dest="ffmpegPath",
		help="Location of ffmpeg binary for imageio.",
	)
	parser.add_argument(
		"--ffmpegLogLevel",
		dest="ffmpegLogLevel",
		type=ast.literal_eval,
		help="Sets verbosity level for ffmpeg logging. ('quiet' (no warnings), 'warning', 'info' (real-time stats)).",
	)
	parser.add_argument(
		"--gpuID",
		dest="gpuID",
		type=ast.literal_eval,
		help="List of integers assigning the gpu index to stream each camera. Set to -1 to stream with CPU.",
	)
	parser.add_argument(
		"--gpuMake",
		dest="gpuMake",
		type=ast.literal_eval,
		help="Company that produced the GPU. Currently supported: 'nvidia', 'amd', 'intel' (QuickSync).",
	)
	parser.add_argument(
		"--codec",
		dest="codec",
		type=ast.literal_eval,
		help="Video codec for compression Currently supported: 'h264', 'h265' (hevc).",
	)
	parser.add_argument(
		"--quality",
		dest="quality",
		type=ast.literal_eval,
		help="Compression quality. Lower number is less compression and larger files. '23' is visually lossless.",
	)
	parser.add_argument(
		"--chunkLengthInSec",
		dest="chunkLengthInSec",
		type=int,
		help="Length of video chunks in seconds for reporting recording progress.",
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

def CheckConfig(params, clargs):
	invalid_keys = []
	for key in params.keys():
		if key not in clargs.__dict__.keys():
			invalid_keys.append(key)

	if len(invalid_keys) > 0:
		invalid_key_msg = [" %s," % key for key in invalid_keys]
		msg = "Unrecognized keys in the configs: %s" % "".join(invalid_key_msg)
		raise ValueError(msg)

def CombineConfigAndClargs(clargs):
	params = LoadConfig(clargs.config)
	CheckConfig(params, clargs)
	for param, value in clargs.__dict__.items():
		if value is not None:
			params[param] = value
	return params

def Main():
	# Optionally, user can manually set path to find ffmpeg binary.
	if params["ffmpegPath"]:
		os.environ["IMAGEIO_FFMPEG_EXE"] = params["ffmpegPath"]

	if sys.platform == "win32":
		pool = mp.Pool(processes=params['numCams'])
		pool.map(AcquireOneCamera, range(0,params['numCams']))

	elif sys.platform == "linux" or sys.platform == "linux2":
		ctx = mp.get_context("spawn")  # for linux compatibility
		pool = ctx.Pool(processes=params['numCams'])
		p = pool.map_async(AcquireOneCamera, range(0,params['numCams']))
		p.get()

parser = argparse.ArgumentParser(
		description="Campy CLI", formatter_class=argparse.ArgumentDefaultsHelpFormatter,
		)
params = ParseClargs(parser)
params = CombineConfigAndClargs(params)