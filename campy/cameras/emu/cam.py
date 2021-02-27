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

	return params["cameraNames"]

def GetDeviceList(system):

	return system

def LoadDevice(cam_params, system, device_list):

	return cam_params["device"]

def GetSerialNumber(device):

	return device

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

def GrabFrames(cam_params, device, writeQueue, dispQueue, stopQueue):
	# Open the camera object
	camera, cam_params = OpenCamera(cam_params, device)

	# Create dictionary for appending frame number and timestamp information
	grabdata = unicam.GrabData(cam_params)
	print(cam_params["cameraName"], "ready to emulate.")

	cnt = 0
	while(True):
		if stopQueue or cnt >= grabdata["numImagesToGrab"]:
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break
		try:
			# Grab image from camera buffer if available
			grabResult = camera.get_data(cnt)

			# Append numpy array to writeQueue for writer to append to file
			writeQueue.append(grabResult)

			# Append timeStamp and frameNumber of grabbed frame to grabdata
			cnt += 1
			grabdata['frameNumber'].append(cnt) # first frame = 1
			grabtime = time.perf_counter()
			grabdata['timeStamp'].append(grabtime)

			if cnt % grabdata["frameRatio"] == 0:
				dispQueue.append(grabResult[::grabdata["ds"],::grabdata["ds"],:])
			if cnt % grabdata["chunkLengthInFrames"] == 0:
				fps_count = int(round(cnt/grabtime))
				print('{} collected {} frames at {} fps.'.format(cam_params["cameraName"], cnt, fps_count))

			# Waits until frame time has been reached to fix frame rate
			while(time.perf_counter() - grabdata['timeStamp'][0] < 1/cam_params["frameRate"]):
				pass

		except Exception as e:
			logging.error('Caught exception in grabFrames: {}'.format(e))
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break

def CloseCamera(cam_params, camera, grabdata):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
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