import os
import sys
import numpy as np
import pandas as pd
import csv
import time
from collections import deque

def ImportCam(cam_params):
	if cam_params["cameraMake"] == "basler":
		from campy.cameras.basler import cam
	elif cam_params["cameraMake"] == "flir":
		from campy.cameras.flir import cam
	elif cam_params["cameraMake"] == "emu":
		from campy.cameras.emu import cam
	return cam

def LoadSystems(params):
	systems = {}
	cam_params = {}
	makes = GetMakeList(params)
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		cam = ImportCam(cam_params)
		systems[makes[m]] = {}
		systems[makes[m]]["system"] = cam.LoadSystem(params)

	return systems

def GetDeviceList(params, systems):
	serials = []
	makes = GetMakeList(params)
	cam_params = {}
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		cam = ImportCam(cam_params)
		system = systems[makes[m]]["system"]
		deviceList = cam.GetDeviceList(system)
		serials = []
		for i in range(len(deviceList)):
			serials.append(cam.GetSerialNumber(deviceList[i]))
		systems[makes[m]]["serials"] = serials
		systems[makes[m]]["deviceList"] = deviceList
	return systems

def LoadDevice(cam_params, systems):
	system = systems[cam_params["cameraMake"]]["system"]
	device_list = systems[cam_params["cameraMake"]]["deviceList"]
	cam = ImportCam(cam_params)
	device = cam.LoadDevice(cam_params, system, device_list)
	return device

def GetMakeList(params):
	cameraMakes = []
	if type(params["cameraMake"]) is list:
		for m in range(len(params["cameraMake"])):
			cameraMakes.append(params["cameraMake"][m])
	elif type(params["cameraMake"]) is str:
		cameraMakes.append(params["cameraMake"])
	makes = list(set(cameraMakes))
	return makes

def GrabData(cam_params):
	grabdata = {"timeStamp": [], "frameNumber": []}

	# Calculate display rate
	if cam_params["displayFrameRate"] <= 0:
		grabdata["frameRatio"] = float('inf')
	elif 0 < cam_params["displayFrameRate"] <= cam_params['frameRate']:
		grabdata["frameRatio"] = int(round(cam_params["frameRate"]/cam_params["displayFrameRate"]))
	else:
		grabdata["frameRatio"] = cam_params["frameRate"]

	# Calculate number of images and chunk length
	grabdata["numImagesToGrab"] = int(round(cam_params["recTimeInSec"]*cam_params["frameRate"]))
	grabdata["chunkLengthInFrames"] = int(round(cam_params["chunkLengthInSec"]*cam_params["frameRate"]))

	return grabdata

def GrabFrames(cam_params, device, writeQueue, dispQueue, stopQueue):
	# Import the cam module
	cam = ImportCam(cam_params)

	# Open the camera object
	camera, cam_params = cam.OpenCamera(cam_params, device)

	# Create dictionary for appending frame number and timestamp information
	grabdata = GrabData(cam_params)

	# Use Basler's default display window on Windows. Not supported on Linux
	if sys.platform == 'win32' and cam_params['cameraMake'] == 'basler':
		dispQueue = cam.OpenImageWindow(cam_params)

	# Start grabbing frames from the camera
	grabbing = cam.StartGrabbing(camera)
	time.sleep(1)
	print(cam_params["cameraName"], "ready to trigger.")
	if cam_params["cameraMake"] == "flir":
		grabTimeOutInMilliseconds = cam_params["grabTimeOutInMilliseconds"]
		print("You have {} seconds to start the recording!".format(grabTimeOutInMilliseconds / 1000))

	while grabbing:
		if stopQueue:
			writeQueue.append('STOP')
			grabbing = False
			cam.CloseCamera(cam_params, camera, grabdata)
			break
		try:
			# Grab image from camera buffer if available
			grabResult = cam.GrabFrame(camera, frameNumber)
		except Exception as err:
			print('No frames received for {} seconds!'.format(grabTimeOutInMilliseconds), err)
			writeQueue.append('STOP')
			grabbing = False
			cam.CloseCamera(cam_params, camera, grabdata)
			break

		try:
			# Append numpy array to writeQueue for writer to append to file
			img = cam.GetImageArray(grabResult, cam_params)
			writeQueue.append(img)
			# Get ImageChunkData and extract TimeStamp and FrameID
			chunkData = cam.GetChunkData()
			timeStamp = cam.GetTimeStamp(chunkData)
			frameNumber = cam.GetFrameID(chunkData)
			# Append timeStamp and frameNumber to grabdata
			grabdata['frameNumber'].append(frameNumber)
			grabdata['timeStamp'].append(timeStamp)
			# ToDo: implement video display
			# if cam_params['displayVideos']:
				# Display converted, downsampled image in the Window
				# if frameNumber % grabdata["frameRatio"] == 0:
				# 	img = cam.DisplayImage(cam_params, dispQueue, grabResult)
			if frameNumber % grabdata["chunkLengthInFrames"] == 0:
				timeElapsed = timeStamp - grabdata["timeStamp"][0]
				fps_count = int(round(frameNumber/(timeElapsed)))
				print('{} collected {} frames at {} fps for {} sec.'\
					.format(cam_params["cameraName"], frameNumber, fps_count, int(round(timeElapsed))))

			cam.ReleaseFrame(grabResult)
		except KeyboardInterrupt:
			pass
		except Exception as e:
			print('Exception in unicam.py GrabFrames', e)
			time.sleep(0.001)

def SaveMetadata(cam_params, grabdata):
	full_folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
	# Zero timeStamps
	timeFirstGrab = grabdata["timeStamp"][0]
	# ToDo: can't remember?
	grabdata["cameraTime"] = grabdata["timeStamp"].copy()
	grabdata["timeStamp"] = [i - timeFirstGrab for i in grabdata["timeStamp"].copy()]
	# Get the frame and time counts to save into metadata
	frame_count = len(grabdata['frameNumber'])
	time_count = grabdata['timeStamp'][-1]
	fps_count = frame_count/time_count
	print('{} saved {} frames at {} fps.'.format(cam_params["cameraName"], frame_count, fps_count))

	while True:
		meta = cam_params
		try:
			npy_filename = os.path.join(full_folder_name, 'frametimes.npy')
			pd_filename = npy_filename[:-3] + '.csv'
			x = np.array([grabdata['frameNumber'], grabdata["cameraTime"], grabdata['timeStamp']])
			df = pd.DataFrame(data=x.T, columns=['frameNumber', 'cameraTime', 'timeStamp'])
			df = df.convert_dtypes({'frameNumber':'int'})
			df.to_csv(pd_filename)
			np.save(npy_filename, x)

		except KeyboardInterrupt:
			break

		csv_filename = os.path.join(full_folder_name, 'metadata.csv')
		meta['totalFrames'] = len(grabdata['frameNumber'])
		meta['totalTime'] = grabdata['timeStamp'][-1]
		keys = meta.keys()
		vals = meta.values()

		try:
			with open(csv_filename, 'w', newline='') as f:
				w = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
				for row in meta.items():
					w.writerow(row)
		except KeyboardInterrupt:
			break

		print('Saved metadata.csv for {}'.format(cam_params['cameraName']))
		break

def CloseSystems(params, systems):
	makes = GetMakeList(params)
	cam_params = {}
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		system = systems[makes[m]]["system"]
		device_list = systems[makes[m]]["deviceList"]
		cam = ImportCam(cam_params)
		try:
			cam.CloseSystem(system, device_list)
		except PySpin.SpinnakerException as ex:
			print('SpinnakerException at unicam.py CloseSystems: %s' % ex)
		except Exception as err:
			print('Exception at unicam.py CloseSystems: %s' % err)
