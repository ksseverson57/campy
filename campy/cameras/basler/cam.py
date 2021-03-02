"""
"""
import pypylon.pylon as pylon
import pypylon.genicam as geni
from campy.cameras import unicam
import os
import time
import logging
import sys
import numpy as np
from collections import deque
import csv

def LoadSystem(params):

	return pylon.TlFactory.GetInstance()

def GetDeviceList(system):

	return system.EnumerateDevices()

def LoadDevice(cam_params, system, device_list):

	return system.CreateDevice(cam_params["device"])

def GetSerialNumber(device):

	return device.GetSerialNumber()

def OpenCamera(cam_params, device):
	camera = pylon.InstantCamera(device)
	camera.Close()
	camera.StopGrabbing()
	camera.Open()

	# Load camera settings
	cam_params = LoadSettings(cam_params, camera)

	print("Opened {}, serial#: {}".format(cam_params["cameraName"], cam_params["cameraSerialNo"]))

	return camera, cam_params

def LoadSettings(cam_params, camera):
	# Load settings from Pylon features file
	pylon.FeaturePersistence.Load(cam_params['cameraSettings'], camera.GetNodeMap(), False) #Validation is false
	
	# Get camera information and save to cam_params for metadata
	cam_params['cameraModel'] = camera.GetDeviceInfo().GetModelName()
	cam_params['frameWidth'] = camera.Width.GetValue()
	cam_params['frameHeight'] = camera.Height.GetValue()
	camera.MaxNumBuffer = 500 # bufferSize is 500 frames

	return cam_params

def OpenImageWindow(cam_params):
	imageWindow = pylon.PylonImageWindow()
	imageWindow.Create(cam_params["n_cam"])
	imageWindow.Show()
	return imageWindow

def StartGrabbing(camera):
	try:
		camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
		return True
	except:
		return False

def GrabFrame(camera, cnt):

	return camera.RetrieveResult(0, pylon.TimeoutHandling_ThrowException)

def GetImageArray(grabResult, cam_params):

	return grabResult.Array

def GetTimeStamp(grabResult, camera):

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

def CloseCamera(cam_params, camera, grabdata):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				camera.Close()
				camera.StopGrabbing()
				unicam.SaveMetadata(cam_params,grabdata)
				time.sleep(1)
				break
			except:
				time.sleep(0.1)
		except KeyboardInterrupt:
			break

def CloseSystem(system, device_list):
	del system
	del device_list
