import os
import sys
import numpy as np
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
	grabdata = {}
	grabdata["timeStamp"] = []
	grabdata["frameNumber"] = []

	# Calculate display rate
	if cam_params["displayFrameRate"] <= 0:
		grabdata["frameRatio"] = float('inf')
	elif cam_params["displayFrameRate"] > 0 and cam_params["displayFrameRate"] <= cam_params['frameRate']:
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
	if sys.platform=='win32' and cam_params['cameraMake'] == 'basler':
		dispQueue = cam.OpenImageWindow(cam_params)

	# Start grabbing frames from the camera
	grabbing = cam.StartGrabbing(camera)
	print(cam_params["cameraName"], "ready to trigger.")

	frameNumber = 0
	while(grabbing):
		if stopQueue or frameNumber >= grabdata["numImagesToGrab"]:
			cam.CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			grabbing = False
			break
		try:
			# Grab image from camera buffer if available
			grabResult = cam.GrabFrame(camera, frameNumber)

			# Append numpy array to writeQueue for writer to append to file
			img = cam.GetImageArray(grabResult, cam_params)
			writeQueue.append(img)

			# Append timeStamp and frameNumber to grabdata
			frameNumber += 1
			grabdata['frameNumber'].append(frameNumber) # first frame = 1
			timeStamp = cam.GetTimeStamp(grabResult, camera)
			grabdata['timeStamp'].append(timeStamp)

			# Display converted, downsampled image in the Window
			if frameNumber % grabdata["frameRatio"] == 0:
				img = cam.DisplayImage(cam_params, dispQueue, grabResult)

			if frameNumber % grabdata["chunkLengthInFrames"] == 0:
				timeElapsed = timeStamp - grabdata["timeStamp"][0]
				fps_count = int(round(frameNumber/(timeElapsed)))
				print('{} collected {} frames at {} fps for {} sec.'\
					.format(cam_params["cameraName"], frameNumber, fps_count, int(round(timeElapsed))))

			cam.ReleaseFrame(grabResult)

		except KeyboardInterrupt:
			pass
		except:
			time.sleep(0.001)

def SaveMetadata(cam_params, grabdata):
	full_folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])

	# Zero timeStamps
	timeFirstGrab = grabdata["timeStamp"][0]
	grabdata["timeStamp"] = [i - timeFirstGrab for i in grabdata["timeStamp"]]

	# Get the frame and time counts to save into metadata
	frame_count = grabdata['frameNumber'][-1]
	time_count = grabdata['timeStamp'][-1]
	fps_count = int(round(frame_count/time_count))
	print('{} saved {} frames at {} fps.'.format(cam_params["cameraName"], frame_count, fps_count))

	while(True):
		meta = cam_params
		try:
			npy_filename = os.path.join(full_folder_name, 'frametimes.npy')
			x = np.array([grabdata['frameNumber'], grabdata['timeStamp']])
			np.save(npy_filename,x)
		except KeyboardInterrupt:
			break

		csv_filename = os.path.join(full_folder_name, 'metadata.csv')
		meta['totalFrames'] = grabdata['frameNumber'][-1]
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

def CloseSystems(params,systems):
	makes = GetMakeList(params)
	cam_params = {}
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		system = systems[makes[m]]["system"]
		device_list = systems[makes[m]]["deviceList"]
		cam = ImportCam(cam_params)
		try:
			cam.CloseSystem(system, device_list)
		except:
			pass
