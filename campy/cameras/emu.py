"""

"""

from campy.cameras import unicam
import os
import time
import logging
import sys
import numpy as np
from collections import deque
import csv
import imageio


class EmulatedCamera:
	# Video reader that serves frames at the configured frame rate,
	# looping back to the start when the video runs out
	def __init__(self, reader, frameRate):
		self.reader = reader
		self.numFrames = reader.count_frames()
		self.framePeriod = 1.0 / frameRate if frameRate > 0 else 0.0
		self.startTime = None

	def get_data(self, frameNumber):
		if self.startTime is None:
			self.startTime = time.perf_counter()
		# Wait until this frame's scheduled time (relative to the first frame)
		delay = self.startTime + frameNumber * self.framePeriod - time.perf_counter()
		if delay > 0:
			time.sleep(delay)
		return self.reader.get_data(frameNumber % self.numFrames)

	def close(self):
		self.reader.close()


def LoadSystem(params):
	# One emulated device per camera, named emu0, emu1, ...: cameraSelection
	# indexes into this list. (It was the string "emu", so cameras past the
	# third indexed past its last character.)
	selection = params.get("cameraSelection", [])
	if not isinstance(selection, list):
		selection = [selection]
	count = max([params["numCams"]] + [s + 1 for s in selection if isinstance(s, int)])
	return ["emu{}".format(n) for n in range(count)]


def GetDeviceList(system):

	return system


def LoadDevice(systems, params, cam_params):

	return cam_params


def GetSerialNumber(device):

	return device


def GetModelName(camera):

	return "Emulated_Camera"


def OpenCamera(cam_params):
	# Open video reader for emulation
	videoFileName = cam_params["videoFilename"][3:len(cam_params["videoFilename"])]
	full_file_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"], videoFileName)
	reader = imageio.get_reader(full_file_name)
	camera = EmulatedCamera(reader, cam_params["frameRate"])

	# Set features manually or automatically, depending on configuration
	frame_size = reader.get_meta_data()['size']
	cam_params['frameWidth'] = frame_size[0]
	cam_params['frameHeight'] = frame_size[1]
	cam_params['cameraModel'] = GetModelName(camera)

	print("Opened {} emulation.".format(cam_params["cameraName"]))
	return camera, cam_params


def LoadSettings(cam_params, camera):

	return cam_params


def StartGrabbing(camera):

	return True


def GrabFrame(camera, frameNumber):

	return camera.get_data(frameNumber)


def GetImageArray(grabResult):

	return grabResult


def GetTimeStamp(grabResult):

	return time.perf_counter()


def DisplayImage(cam_params, dispQueue, grabResult):
	# Downsample image
	img = grabResult[::cam_params["displayDownsample"],::cam_params["displayDownsample"],:]

	# Send to display queue
	dispQueue.append(img)


def ReleaseFrame(grabResult):

	del grabResult


def CloseCamera(cam_params, camera):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close camera after acquisition stops
	camera.close()
	del camera


def CloseSystem(system, device_list):
	del system
	del device_list
