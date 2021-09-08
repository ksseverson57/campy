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
	# system = params["systems"]["basler"]["system"]
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


def GetImageArray(grabResult):

	return grabResult.Array


def GetTimeStamp(grabResult):

	return grabResult.TimeStamp*1e-9


def DisplayImage(cam_params, dispQueue, grabResult):
	# Basler display window is more performant than generic matplot figure
	if sys.platform == 'win32':
		dispQueue.SetImage(grabResult)
		dispQueue.Show()
	else:
		# If pixelformat is bayer, first convert result to RGB
		if cam_params["pixelFormatInput"].find("bayer") != -1:
			converter = pylon.ImageFormatConverter()
			converter.OutputPixelFormat = pylon.PixelType_RGB8packed
			img = converter.Convert(grabResult).GetArray()
		else:
			img = grabResult.GetArray()

		# Downsample image
		img = img[::cam_params["displayDownsample"],::cam_params["displayDownsample"]]

		# Send image to display window thru queue
		dispQueue.append(img)


def ReleaseFrame(grabResult):

	grabResult.Release()


def CloseCamera(cam_params, camera):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close Basler camera after acquisition stops
	camera.StopGrabbing()
	camera.Close()


def CloseSystem(system, device_list):
	del system
	del device_list


# Basler-Specific Functions
def OpenPylonImageWindow(cam_params):
	imageWindow = pylon.PylonImageWindow()
	imageWindow.Create(cam_params["n_cam"])
	imageWindow.Show()
	return imageWindow
