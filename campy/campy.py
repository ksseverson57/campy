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
from campy import writer, display, configurator, startup, statusline
from campy.trigger import trigger
from campy.cameras import unicam
from campy.utils.utils import HandleKeyboardInterrupt, StartPrinter, StopPrinter

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


def InitCameraProcess(counters):
	# Each camera process, as the pool starts it: the counters the status line reads (statusLine)
	statusline.UseCounters(counters)


def AcquireOneCamera(n_cam):
	# What this camera process prints is written by a thread of its own, so a
	# slow console or log file never holds up the camera; all of it is written
	# before the process ends, even when it fails
	StartPrinter()
	try:
		RecordOneCamera(n_cam)
	finally:
		startup.Failed() # with consoleSummary, a camera that never got ready: what it did as it opened
		StopPrinter()


def RecordOneCamera(n_cam):
	# Initialize param dictionary for this camera stream
	cam_params = configurator.ConfigureCamParams(systems, params, n_cam)

	# Initialize queues for display, video writer, and stop messages
	dispQueue = deque([], 2)
	writeQueue = deque()
	stopReadQueue = deque([],1)
	stopWriteQueue = deque([],1)

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


def Main():
	# Optionally, one status line on the console while recording (statusLine), drawn
	# from counters the camera processes share
	mode = statusline.Prepare(params)
	counters = statusline.MakeCounters(params["numCams"]) if mode else None
	with HandleKeyboardInterrupt():
		# Acquire cameras in parallel with Windows- and Linux-compatible pool
		p = mp.get_context("spawn").Pool(params["numCams"], initializer=InitCameraProcess, initargs=(counters,))
		line = None
		if mode:
			names = [params["cameraNames"][n] for n in range(params["numCams"])]
			line = statusline.StatusLine(mode, counters, names).Start()
		try:
			p.map_async(AcquireOneCamera,range(params["numCams"])).get()
		finally:
			if line is not None:
				line.Stop()

	CloseSystems(systems, params)

# In a camera process, when the main process shows the status line, each line
# printed wipes it first (statusLine)
statusline.Child()

# Open systems, creates global 'systems' and 'params' variables
systems, params = OpenSystems()