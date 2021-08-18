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

def LoadSystem(params):

	return params["cameraMake"]


def GetDeviceList(system):

	return system


def LoadDevice(cam_params):

	return cam_params["device"]


def GetSerialNumber(device):

	return device


def GetModelName(camera):

	return "Emulated_Camera"


def OpenCamera(cam_params, device):
	# Open video reader for emulation
	videoFileName = cam_params["videoFilename"][3:len(cam_params["videoFilename"])]
	full_file_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"], videoFileName)
	camera = imageio.get_reader(full_file_name)

	# Set features manually or automatically, depending on configuration
	frame_size = camera.get_meta_data()['size']
	cam_params['frameWidth'] = frame_size[0]
	cam_params['frameHeight'] = frame_size[1]

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
	del camera


def CloseSystem(system, device_list):
	del system
	del device_list
