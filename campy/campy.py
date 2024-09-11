"""
CamPy: Python-based multi-camera recording software.
Integrates machine vision camera APIs with ffmpeg real-time compression.
Outputs one MP4 video file and metadata files for each camera

"campy" is the main console. 
User inputs are loaded from config yaml file using a command line interface (CLI) 
cli parses the config arguments (and default params) into "params" dictionary.
cli assigns params to each camera stream in the "cam_params" dictionary.
	* Camera index is set by "cameraSelection".
	* If param is string, it is applied to all cameras.
	* If param is list of strings, it is assigned to each camera, ordered by camera index.
Camera streams are acquired and encoded in parallel using multiprocessing.

Usage: 
campy-acquire ./configs/campy_config.yaml
"""

import os, time, sys, logging, threading, queue
from collections import deque
import multiprocessing as mp
from campy import writer, display, cli
from campy.trigger import trigger
from campy.cameras import unicam
from campy.utils.utils import HandleKeyboardInterrupt


def OpenSystems():
	# Configure parameters
	params = cli.ConfigureParams()

	# Load Camera Systems and Devices
	systems = unicam.LoadSystems(params)
	systems = unicam.GetDeviceList(systems, params)

	return systems, params


def AcquireOneCamera(n_cam):
	# Initialize param dictionary for this camera stream
	cam_params = cli.ConfigureCamParams(systems, params, n_cam)

	if n_cam == 0:
		cam_params["triggers"] = trigger.StartTriggers(systems, params)
	else:
		time.sleep(3)

	# Initialize queues for display, timestamper, video writer, and stop messages
	dispQueue = deque([], 2)
	writeQueue = deque()
	stampQueue = deque([])
	stopGrabQueue = deque([],1)
	stopReadQueue = deque([],1)
	stopWriteQueue = deque([],1)

	# Open image display window ("consumer" thread)
	threading.Thread(
		target = display.DisplayFrames,
		daemon = True,
		args = (
			cam_params, 
			dispQueue,
			),
		).start()

	# Start framegrabber ("producer" thread)
	threading.Thread(
		target = unicam.GrabFrames,
		daemon = True,
		args = (
			cam_params, 
			writeQueue, 
			dispQueue, 
			stopGrabQueue,
			stopReadQueue,
			stopWriteQueue,
			),
		).start()

	# Start timestamper ("consumer thread" within Writer)
	threading.Thread(
		target = writer.SaveTimestamps,
		daemon = True,
		args = (cam_params, stampQueue,),
		).start()

	# Start video writer (main "consumer" process)
	writer.WriteFrames(
		cam_params,
		writeQueue,
		stopGrabQueue,
		stopReadQueue,
		stopWriteQueue,
		stampQueue,
		)


def Main():
	with HandleKeyboardInterrupt():
		# Acquire cameras in parallel with OS-agnostic pool
		p = mp.get_context("spawn").Pool(params["numCams"])
		p.map_async(AcquireOneCamera, range(params["numCams"])).get()

	unicam.CloseSystems(systems, params)


# Open 'systems' and 'params' global variables
systems, params = OpenSystems()
