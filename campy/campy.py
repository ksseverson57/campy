"""
CamPy: Python-based multi-camera recording software.
Integrates machine vision camera APIs with ffmpeg real-time compression.
Outputs one MP4 video file and metadata files for each camera

"campy" is the main console. 
User inputs are loaded from config yaml file using a command line interface (CLI) 
configurator parses the config arguments (and default params) into "params" dictionary.
configurator assigns params to each camera stream in the "cam_params" dictionary.
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
from campy import writer, display, configurator, windowfeed
from campy.trigger import trigger
from campy.cameras import unicam
from campy.utils.utils import HandleKeyboardInterrupt
from campy.utils import folders

def OpenSystems():
	# Configure parameters
	params = configurator.ConfigureParams()

	# Load Camera Systems and Devices
	systems = unicam.LoadSystems(params)
	systems = unicam.GetDeviceList(systems, params)

	# Start camera triggers if configured
	systems = trigger.StartTriggers(systems, params)

	return systems, params


def CloseSystems(systems, params):
	trigger.StopTriggers(systems, params)
	unicam.CloseSystems(systems, params)


def AcquireOneCamera(n_cam):
	# Initialize param dictionary for this camera stream
	cam_params = configurator.ConfigureCamParams(systems, params, n_cam)

	# Initialize queues for display, video writer, and stop messages
	writeQueue = deque()
	stopReadQueue = deque([],1)
	stopWriteQueue = deque([],1)

	if cam_params["displayMode"] == "one-window":
		# Send frames to the window that shows every camera (campy/window.py)
		dispQueue = windowfeed.Feed(cam_params, windowfeed.queues[n_cam])
	else:
		dispQueue = deque([], 2)

		# Start image window display thread
		threading.Thread(
			target = display.DisplayFrames,
			daemon = True,
			args = (cam_params, dispQueue,),
			).start()

	# Start grabbing frames ("producer" thread)
	threading.Thread(
		target = unicam.GrabFrames,
		daemon = True,
		args = (cam_params, writeQueue, dispQueue, stopReadQueue, stopWriteQueue,),
		).start()

	# Start video file writer (main "consumer" process)
	writer.WriteFrames(cam_params, writeQueue, stopReadQueue, stopWriteQueue)


def UseRecordingFolder(folder):
	# In each camera process: record into this run's folder (sessionFolder)
	params["recordingFolder"] = folder


def StartCameraProcess(cameraQueues, folder):
	# Pool initializer: each camera process gets the one window's queues
	# (displayMode "one-window") and this run's folder (sessionFolder)
	if cameraQueues is not None:
		windowfeed.SetQueues(cameraQueues)
	if folder is not None:
		UseRecordingFolder(folder)


def Main():
	# sessionFolder: this run's own new folder inside videoFolder, made once
	# here. The camera processes read the config again, so they are told which.
	folder = None
	if folders.SessionFolders(params):
		folders.CheckCameraNames(params)
		folder = folders.MakeSessionFolder(params["videoFolder"])
		UseRecordingFolder(folder)
		print("Recording into {}".format(folder), flush=True)

	with HandleKeyboardInterrupt():
		# Acquire cameras in parallel with Windows- and Linux-compatible pool
		ctx = mp.get_context("spawn")
		if params["displayMode"] == "one-window":
			# One window, in a process of its own, shows every camera
			window = windowfeed.WindowProcess(ctx, params)
		else:
			window = None
		p = ctx.Pool(params["numCams"], StartCameraProcess, (window.queues if window else None, folder))
		try:
			p.map_async(AcquireOneCamera,range(params["numCams"])).get()
		finally:
			if window is not None:
				window.Stop()

	CloseSystems(systems, params)

# Open systems, creates global 'systems' and 'params' variables
# (but not in the process of the window that shows every camera, which only draws frames)
if mp.current_process().name != windowfeed.PROCESS_NAME:
	systems, params = OpenSystems()