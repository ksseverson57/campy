"""
CamPy: Python-based multi-camera recording software.
Integrates machine vision camera APIs with ffmpeg real-time compression.
Outputs one MP4 video file for each camera and metadata files

'campy' is the main console. 
User inputs are loaded from config yaml file using a command line interface (CLI) into the 'params' dictionary.
Params are assigned to each camera stream in the 'cam_params' dictionary.
	* Camera index is set by 'cameraSelection'.
	* If param is string, it is applied to all cameras.
	* If param is list of strings, it is assigned to each camera, ordered by camera index.
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
from campy.cameras import unicam
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import ast
import yaml
import logging
import serial

def CombineConfigAndClargs(clargs):
	params = LoadConfig(clargs.config)
	CheckConfig(params, clargs)
	for key, value in clargs.__dict__.items():
		if value is not None:
			params[key] = value
	return params

def CheckConfig(params, clargs):
	default_params = CampyParams()
	for key,value in default_params.items():
		if key not in params.keys():
			params[key] = value

	invalid_keys = []
	for key in params.keys():
		if key not in clargs.__dict__.keys():
			invalid_keys.append(key)

	if len(invalid_keys) > 0:
		invalid_key_msg = [" %s," % key for key in invalid_keys]
		msg = "Unrecognized keys in the configs: %s" % "".join(invalid_key_msg)
		raise ValueError(msg)

def LoadConfig(config_path):
	try:
		with open(config_path, 'rb') as f:
			config = yaml.safe_load(f)
	except Exception as e:
		logging.error('Caught exception: {}'.format(e))
	return config

def LoadSystemsAndDevices(params):
	params = unicam.LoadSystems(params)
	params = unicam.GetDeviceList(params)
	return params

def CreateCamParams(params, n_cam):
	# Insert camera-specific metadata from parameters into cam_params dictionary
	cam_params = params
	cam_params["n_cam"] = n_cam
	cam_params["baseFolder"] = os.getcwd()
	cam_params["cameraName"] = params["cameraNames"][n_cam]

	# Default configuration parameters dictionary.
	# Default value is used if variable is either not present in config or not overwritten by cameraSettings.
	default_params = {"frameRate": 100,
						"cameraSelection": n_cam,
						"cameraSettings": "./campy/cameras/basler/settings/acA1920-150uc_1152x1024p_100fps_trigger_RGB_p6.pfs",
						"cameraMake": "basler", 
						"cameraTrigger": "Line0", 
						"cameraExposureTimeInMs": 2000,
						"cameraGain": 1,
						"pixelFormatInput": "rgb24", 
						"pixelFormatOutput": "rgb0", 
						"frameWidth": 1152,
						"frameHeight": 1024,
						"ffmpegLogLevel": "quiet",
						"gpuID": -1,
						"gpuMake": "nvidia",
						"codec": "h264",
						"quality": 21,
						"chunkLengthInSec": 30,
						"displayFrameRate": 10,
						"displayDownsample": 2,
						"startArduino": 0,
						"serialPort": 'COM3'}

	cam_params = OptParams(params, cam_params, default_params)
	cam_params["device"] = params["systems"][cam_params["cameraMake"]]["deviceList"][cam_params["cameraSelection"]]
	cam_params = unicam.LoadDevice(params, cam_params)
	cam_params["cameraSerialNo"] = params["systems"][cam_params["cameraMake"]]["serials"][cam_params["cameraSelection"]]
	return cam_params

def OptParams(params, cam_params, default_params):
	# Optionally, user provides a single string or a list of strings, equal in size to numCams
	# String is passed to all cameras. Else, each list item is passed to its respective camera
	opt_params_list = list(default_params)
	for i in range(len(opt_params_list)):
		key = opt_params_list[i]
		if key in params:
			if type(params[key]) is list:
				if len(params[key]) == params["numCams"]:
					cam_params[key] = params[key][cam_params["n_cam"]]
				else: print('{} list is not the same size as numCams.'.format(key))
		else:
			cam_params[key] = default_params[key]
	return cam_params

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
		type=int, 
		help="Frame rate equal to trigger frequency.",
	)
	parser.add_argument(
		"--recTimeInSec",
		dest="recTimeInSec",
		type=int,
		help="Recording time in seconds.",
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
		type=int,
		help="Selects and orders camera indices to include in the recording. List length must be equal to numCams",
	)
	parser.add_argument(
		"--cameraSettings", 
		dest="cameraSettings",
		type=ast.literal_eval, 
		help="Path to camera settings file.",
	)
	parser.add_argument(
		"--cameraTrigger", 
		dest="cameraTrigger",
		type=ast.literal_eval, 
		help="String indicating trigger input to camera (e.g. 'Line3').",
	)
	parser.add_argument(
		"--cameraOut", 
		dest="cameraOut",
		type=int, 
		help="Integer indicating camera output line for exposure active signal (e.g. 2).",
	)
	parser.add_argument(
		"--cameraExposureTimeInMs", 
		dest="cameraExposureTimeInMs",
		type=int, 
		help="Exposure time for each camera frame.",
	)
	parser.add_argument(
		"--cameraGain", 
		dest="cameraGain",
		type=float, 
		help="Intensity gain applied to each camera frame.",
	)
	parser.add_argument(
		"--frameHeight", 
		dest="frameHeight",
		type=int, 
		help="Frame height in pixels.",
	)
	parser.add_argument(
		"--frameWidth", 
		dest="frameWidth",
		type=int, 
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
		type=int,
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
		type=int,
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
	parser.add_argument(
		"--startArduino",
		dest="startArduino",
		type=int,
		help="If True, start arduino after initializing cameras.",
	)
	parser.add_argument(
		"--serialPort",
		dest="serialPort",
		type=ast.literal_eval,
		help="Serial port for communicating with Arduino.",
	)

	return parser.parse_args()

def AcquireOneCamera(n_cam):
	# Initializes metadata dictionary for this camera stream
	# and inserts important configuration details

	# Load camera parameters from config
	cam_params = CreateCamParams(params, n_cam)

	# Import the correct camera module for your camera
	print('Importing {} cam for {}'.format(cam_params["cameraMake"], cam_params["cameraName"]))
	cam = unicam.ImportCam(cam_params)

	# Initialize queues for video writer and stop message
	writeQueue = deque()
	stopQueue = deque([], 1)

	# Start image window display thread
	dispQueue = deque([], 2)
	threading.Thread(
		target = display.DisplayFrames,
		daemon = True,
		args = (cam_params, dispQueue,),
		).start()

	# Start grabbing frames ('producer' thread)
	threading.Thread(
		target = unicam.GrabFrames,
		daemon = True,
		args = (cam_params, writeQueue, dispQueue, stopQueue,),
		).start()

	# Start video file writer (main 'consumer' thread)
	campipe.WriteFrames(cam_params, writeQueue, stopQueue)

	# Close the systems and devices properly
	# unicam.CloseSystems(params)

def Main():
	# Optionally, user can manually set path to find ffmpeg binary.
	if params["ffmpegPath"]:
		os.environ["IMAGEIO_FFMPEG_EXE"] = params["ffmpegPath"]

	# If desired, start the arduino.
	# The arduino sketch delays prior to starting to allow the cameras to initialize. 
	if params["startArduino"]:
		try:
			print('Opening arduino port {}'.format(params["serialPort"]), flush=True)
			ser = serial.Serial(port=params["serialPort"], baudrate=115200, timeout=0.1)
			print("Starting arduino loop", flush=True)
			time.sleep(2)
			ser.write(str(params["frameRate"]).encode('utf-8'))
			print("Arduino is ready to trigger!", flush=True)
		except Exception as e:
			logging.error('Caught exception: {}'.format(e))

	if sys.platform == "win32":
		pool = mp.Pool(processes=params['numCams'])
		pool.map(AcquireOneCamera, range(0,params['numCams']))

	elif sys.platform == "linux" or sys.platform == "linux2":
		ctx = mp.get_context("spawn")  # for linux compatibility
		pool = ctx.Pool(processes=params['numCams'])
		p = pool.map_async(AcquireOneCamera, range(0,params['numCams']))
		p.get()

	unicam.CloseSystems(params)

parser = ArgumentParser(
	description="Campy CLI", 
	formatter_class=ArgumentDefaultsHelpFormatter,
	)
clargs = ParseClargs(parser)
params = CombineConfigAndClargs(clargs)
params = LoadSystemsAndDevices(params)