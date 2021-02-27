"""

"""

import pypylon.pylon as pylon
import pypylon.genicam as geni
from campy.cameras import cameras
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

	# Load settings from Pylon features file
	pylon.FeaturePersistence.Load(cam_params['cameraSettings'], camera.GetNodeMap(), False) #Validation is false

	# Get camera information and save to cam_params for metadata
	cam_params['cameraModel'] = camera.GetDeviceInfo().GetModelName()
	cam_params['frameWidth'] = camera.Width.GetValue()
	cam_params['frameHeight'] = camera.Height.GetValue()

	# Start grabbing frames (OneByOne = first in, first out)
	camera.MaxNumBuffer = 500 # bufferSize is 500 frames
	print("Opened {}, serial#: {}".format(cam_params["cameraName"], cam_params["cameraSerialNo"]))

	return camera, cam_params

def GrabFrames(cam_params, device, writeQueue, dispQueue, stopQueue):
	# Open the camera object
	camera, cam_params = OpenCamera(cam_params, device)

	# Create dictionary for appending frame number and timestamp information
	grabdata = unicam.GrabData(cam_params)

	# Use Basler's default display window. Works on Windows. Not supported on Linux
	if sys.platform=='win32' and cam_params['cameraMake'] == 'basler':
		imageWindow = pylon.PylonImageWindow()
		imageWindow.Create(cam_params["n_cam"])
		imageWindow.Show()

	# Start grabbing frames from the camera using first-in-first-out buffer
	camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
	print("{} ready to trigger.".format(cam_params["cameraName"]))

	cnt = 0
	while(camera.IsGrabbing()):
		if stopQueue or cnt >= grabdata["numImagesToGrab"]:
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break
		try:
			# Grab image from camera buffer if available
			grabResult = camera.RetrieveResult(0, pylon.TimeoutHandling_ThrowException) # Timeout is 0

			# Append numpy array to writeQueue for writer to append to file
			writeQueue.append(grabResult.Array)

			# Append timeStamp and frameNumber of grabbed frame to grabdata
			cnt += 1
			grabdata['frameNumber'].append(cnt) # first frame = 1
			grabtime = grabResult.TimeStamp/1e9
			grabdata['timeStamp'].append(grabtime)	

			if cnt % grabdata["frameRatio"] == 0:
				if sys.platform == 'win32' and cam_params['cameraMake'] == 'basler':
					try:
						imageWindow.SetImage(grabResult)
						imageWindow.Show()
					except Exception as e:
						logging.error('Caught exception: {}'.format(e))
				else:
					dispQueue.append(grabResult.Array[::grabdata["ds"],::grabdata["ds"]])

			if cnt % grabdata["chunkLengthInFrames"] == 0:
				fps_count = int(round(cnt/grabtime))
				print('{} collected {} frames at {} fps.'.format(cam_params["cameraName"], cnt, fps_count))

			grabResult.Release()

		# Else wait for next frame available
		except geni.GenericException:
			time.sleep(0.0001)
		except Exception as e:
			logging.error('Caught exception: {}'.format(e))

def CloseCamera(cam_params, camera, grabdata):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				unicam.SaveMetadata(cam_params,grabdata)
				time.sleep(1)
				camera.Close()
				camera.StopGrabbing()
				break
			except:
				time.sleep(0.1)
		except KeyboardInterrupt:
			break

def CloseSystem(system, device_list):
	del system
	del device_list
