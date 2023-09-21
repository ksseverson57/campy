"""
"""
import pypylon.pylon as pylon
import pypylon.genicam as geni
from campy.cameras import unicam
import os, sys, time, logging
import numpy as np
from collections import deque


def LoadSystem(params):

	return pylon.TlFactory.GetInstance()


def GetDeviceList(system):

	return system.EnumerateDevices()


def LoadDevice(systems, params, cam_params):
	system = systems["basler"]["system"]
	cam_params["camera"] = system.CreateDevice(cam_params["device"])
	return cam_params


def GetSerialNumber(device):

	return device.GetSerialNumber()


def GetModelName(camera):

	return camera.GetDeviceInfo().GetModelName()


def OpenCamera(cam_params):
	# Open the camera
	camera = pylon.InstantCamera(cam_params["camera"])
	camera.Open()

	# Load default camera settings
	cam_params['cameraModel'] = GetModelName(camera)
	cam_params = LoadSettings(cam_params, camera)

	return camera, cam_params


def LoadSettings(cam_params, camera):
	# Load settings from Pylon features file
	pylon.FeaturePersistence.Load(cam_params['cameraSettings'], camera.GetNodeMap(), False) #Validation is false
	camera.MaxNumBuffer = cam_params["bufferSize"] # default bufferSize is ~500 frames

	# Manual override settings
	if cam_params["cameraTrigger"] == "Software" or cam_params["cameraTrigger"] == "software":
		camera.TriggerMode.SetValue('Off')
		camera.AcquisitionFrameRateEnable.SetValue(True)
		camera.AcquisitionFrameRate.SetValue(cam_params["frameRate"])
	
	# Get camera information and save to cam_params for metadata
	cam_params['frameWidth'] = camera.Width.GetValue()
	cam_params['frameHeight'] = camera.Height.GetValue()

	return cam_params


def StartGrabbing(camera):
	try:
		camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
		return True
	except Exception:
		return False


def GrabFrame(camera, frameNumber):

	return camera.RetrieveResult(0, pylon.TimeoutHandling_ThrowException)


def GrabSucceeded(grabResult):
	
	return grabResult.GrabSucceeded()


def GetImageArray(grabResult):

	return grabResult.GetArrayZeroCopy()


def CopyImageArray(grabResult):

	return grabResult.Array


def GetTimeStamp(grabResult):

	return grabResult.TimeStamp*1e-9


def DisplayImage(cam_params, dispQueue, grabResult, converter=None):
	try:
		# Copy RGB image
		if cam_params["pixelFormatInput"].find("bayer") != -1:
			img = ConvertBayerToRGB(converter, grabResult)
		else:
			img = CopyImageArray(grabResult)

		# Downsample image
		img = img[::cam_params["displayDownsample"],::cam_params["displayDownsample"]]

		# Convert to BGR for opencv
		if img.ndim == 3:
			img = img[...,::-1]

		# Queue image for display in opencv window
		dispQueue.append(img)
	except Exception as e:
		if cam_params["camera_debug"]:
			print(e)


def ReleaseFrame(grabResult):
	# memory buffer is released in the zero-copy context manager
	grabResult.Release()


def CloseCamera(cam_params, camera):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close Basler camera after acquisition stops
	camera.StopGrabbing()
	camera.Close()


def CloseSystem(system, device_list):
	del system
	del device_list


# Basler-specific functions
def GetConverter():
	converter = pylon.ImageFormatConverter()
	converter.OutputPixelFormat = pylon.PixelType_RGB8packed
	return converter


def ConvertBayerToRGB(converter, grabResult):
	img = converter.Convert(grabResult)
	return img.Array
