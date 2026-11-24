"""
"""

import os, ast, yaml, time, logging
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from campy.cameras import unicam


def DefaultParams():
	"""
	Default parameters for campy config.
	Omitted parameters will revert to these default values.
	""" 

	params = {}
	# Recording default parameters
	params["numCams"] = 1
	params["videoFolder"] = "./test"
	params["videoFilename"] = "0.mp4"
	params["frameRate"] = 100
	params["recTimeInSec"] = 10

	# Camera default parameters
	params["cameraMake"] = "basler"
	params["cameraSettings"] = "None"
	params["frameWidth"] = 1152
	params["frameHeight"] = 1024
	params["cameraDebug"] = False

	# Flir camera default parameters
	params["cameraTrigger"] = "None" # "Line3"
	params["cameraOut"] = 2
	params["bufferMode"] = "OldestFirst"
	params["bufferSize"] = 100
	params["cameraExposureTimeInUs"] = 1500
	params["cameraGain"] = 1
	params["disableGamma"] = True

	# Compression default parameters
	params["ffmpegLogLevel"] = "quiet"
	params["ffmpegPath"] = "None" # "/home/usr/Documents/ffmpeg/ffmpeg"
	params["pixelFormatInput"] = "rgb24" # "bayer_bggr8" "rgb24"
	params["pixelFormatOutput"] = "rgb0"
	params["gpuID"] = -1
	params["gpuMake"] = "nvidia"
	params["codec"] = "h264"  
	params["quality"] = 21
	params["preset"] = "None"

	# Display parameters
	params["chunkLengthInSec"] = 5
	params["displayFrameRate"] = 10
	params["displayDownsample"] = 2

	# Trigger parameters
	params["triggerController"] = "arduino"
	params["startArduino"] = False
	params["serialPort"] = "COM3"
	params["digitalPins"] = [0,1,2,3,4,5,6]

	return params


def AutoParams(params, default_params):
	# Handle out of range values (reset to default)
	range_params = [
		"numCams",
		"frameRate",
		"recTimeInSec",
		"frameHeight",
		"frameWidth",
		"bufferSize",
		"cameraGain",
		"cameraExposureTimeInUs",
		"quality",
		"chunkLengthInSec",
		"displayFrameRate",
		"displayDownsample",
		]

	for i in range(len(range_params)):
		key = range_params[i]
		default_value = default_params[key]
		if params[key] <= 0:
			params[key] = default_value
			print("{} set to invalid value in config. Setting to default ({})."\
					.format(key, default_value))

	# Handle missing config parameters
	if "numCams" in params.keys():
		if "cameraNames" not in params.keys():
			params["cameraNames"] = ["Camera%s" % n for n in range(params["numCams"])]
		if "cameraSelection" not in params.keys():
			params["cameraSelection"] = [n for n in range(params["numCams"])]
	else:
		print("Please configure 'numCams' to the number of cameras you want to acquire.")

	return params


def ConfigureParams():
	parser = ArgumentParser(description="Campy CLI", 
						formatter_class=ArgumentDefaultsHelpFormatter,)
	clargs = ParseClargs(parser)
	params = CombineConfigAndClargs(clargs)

	# Optionally, user can manually set path to find ffmpeg binary.
	if params["ffmpegPath"] is not "None":
		os.environ["IMAGEIO_FFMPEG_EXE"] = params["ffmpegPath"]

	return params


def ConfigureCamParams(systems, params, n_cam):
	# Insert camera-specific metadata from parameters into cam_params dictionary
	cam_params = params
	cam_params["n_cam"] = n_cam
	cam_params["baseFolder"] = os.getcwd()
	cam_params["cameraName"] = params["cameraNames"][n_cam]

	cam_params = OptParams(cam_params)
	cam_make = cam_params["cameraMake"]
	cam_idx = cam_params["cameraSelection"]

	cam_params["device"] = systems[cam_make]["deviceList"][cam_idx]
	cam_params = unicam.LoadDevice(systems, params, cam_params)

	cam_params["cameraSerialNo"] = systems[cam_make]["serials"][cam_idx]

	return cam_params


def OptParams(cam_params):
	# Optionally, user provides a single string or a list of strings, equal in size to numCams
	# String is passed to all cameras. Else, each list item is passed to its respective camera
	for key in cam_params:
		if type(cam_params[key]) is list:
			if len(cam_params[key]) == cam_params["numCams"]:
				cam_params[key] = cam_params[key][cam_params["n_cam"]]
			elif key == "digitalPins":
				continue
			else:
				logging.warning("{} size mismatch with numCams. Using list idx {}."\
						.format(key,cam_params["n_cam"]))
				cam_params[key] = cam_params[key][cam_params["n_cam"]]
	return cam_params


def CheckConfig(params, clargs):
	default_params = DefaultParams()
	for key,value in default_params.items():
		if key not in params.keys():
			params[key] = value

	auto_params = AutoParams(params, default_params)
	for key,value in auto_params.items():
		params[key] = value

	invalid_keys = []
	for key in params.keys():
		if key not in clargs.__dict__.keys():
			invalid_keys.append(key)

	if len(invalid_keys) > 0:
		invalid_key_msg = [" %s," % key for key in invalid_keys]
		msg = "Unrecognized keys in the config: %s" % "".join(invalid_key_msg)
		raise ValueError(msg)

	return params


def LoadConfig(config_path):
	try:
		with open(config_path, "rb") as f:
			config = yaml.safe_load(f)
	except Exception as e:
		logging.error('Caught this error at configurator.py LoadConfig: {}. Check your config path!'.format(e))
		raise
	return config


def CombineConfigAndClargs(clargs):
	params = LoadConfig(clargs.config)
	params = CheckConfig(params, clargs)
	for key, value in clargs.__dict__.items():
		if value is not None:
			params[key] = value
	return params


def ParseClargs(parser):
	parser.add_argument(
		"config", metavar="config", help="Campy configuration .yaml file.",
	)

	# Recording arguments
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
		type=float, 
		help="Frame rate equal to trigger frequency.",
	)
	parser.add_argument(
		"--recTimeInSec",
		dest="recTimeInSec",
		type=float,
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
		help="Selects and orders camera indices to include in the recording. \
				List length must be equal to numCams",
	)

	# Camera arguments. May be specific to particular camera make
	parser.add_argument(
		"--cameraMake", 
		dest="cameraMake", 
		type=ast.literal_eval,
		help="Company that produced the camera. Currently supported: 'basler', 'flir'.",
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
		"--cameraDebug", 
		dest="cameraDebug",
		type=bool, 
		help="Flag to turn on camera debug mode.",
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
		"--cameraExposureTimeInUs", 
		dest="cameraExposureTimeInUs",
		type=int, 
		help="Exposure time (in microseconds) for each camera frame.",
	)
	parser.add_argument(
		"--cameraGain", 
		dest="cameraGain",
		type=float, 
		help="Intensity gain applied to each camera frame.",
	)
	parser.add_argument(
		"--disableGamma", 
		dest="disableGamma",
		type=bool, 
		help="Whether to disable gamma (default: True).",
	)
	parser.add_argument(
		"--bufferMode", 
		dest="bufferMode",
		type=ast.literal_eval, 
		help="Type of buffer to use in camera (default: 'OldestFirst').",
	)
	parser.add_argument(
		"--bufferSize", 
		dest="bufferSize",
		type=int, 
		help="Size of buffer to use in camera in frames (default: 100).",
	)

	# ffmpeg arguments
	parser.add_argument(
		"--ffmpegPath",
		dest="ffmpegPath",
		help="Location of ffmpeg binary for imageio.",
	)
	parser.add_argument(
		"--ffmpegLogLevel",
		dest="ffmpegLogLevel",
		type=ast.literal_eval,
		help="Sets verbosity level for ffmpeg logging. ('quiet' (no warnings), \
			'warning', 'info' (real-time stats)).",
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
		"--gpuID",
		dest="gpuID",
		type=int,
		help="List of integers assigning the gpu index to stream each camera. \
			Set to -1 to stream with CPU.",
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
		help="Compression quality. Lower number is less compression and larger files. \
			'23' is visually lossless.",
	)
	parser.add_argument(
		"--preset",
		dest="preset",
		type=ast.literal_eval,
		help="Compression preset (e.g. 'slow', 'fast', 'veryfast'). \
				Incorrect settings may break the pipe. Test with ffmpegLogLevel 'warning' or 'info'.",
	)

	# Display and CLI feedback arguments
	parser.add_argument(
		"--chunkLengthInSec",
		dest="chunkLengthInSec",
		type=float,
		help="Length of video chunks in seconds for reporting recording progress.",
	)
	parser.add_argument(
		"--displayFrameRate",
		dest="displayFrameRate",
		type=float,
		help="Display frame rate in Hz. Max ~30.",
	)
	parser.add_argument(
		"--displayDownsample",
		dest="displayDownsample",
		type=int,
		help="Downsampling factor for displaying images.",
	)

	# Microcontroller triggering arguments
	parser.add_argument(
		"--triggerController",
		dest="triggerController",
		type=ast.literal_eval,
		help="Microntroller make for camera triggering. Currently supported: 'arduino'.",
	)
	parser.add_argument(
		"--startArduino",
		dest="startArduino",
		type=bool,
		help="If True, start Arduino after initializing cameras.",
	)
	parser.add_argument(
		"--serialPort",
		dest="serialPort",
		type=ast.literal_eval,
		help="Serial port for communicating with Arduino.",
	)
	parser.add_argument(
		"--digitalPins",
		dest="digitalPins",
		type=int,
		help="Digital pins on microcontroller board for sending TTL camera triggers.",
	)

	return parser.parse_args()

