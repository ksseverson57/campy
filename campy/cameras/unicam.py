import os
import sys
import numpy as np
import csv
import time
from collections import deque
import logging
from scipy import io as sio
	
def ImportCam(cam_params):
	if cam_params["cameraMake"] == "basler":
		from campy.cameras.basler import cam
	elif cam_params["cameraMake"] == "flir":
		from campy.cameras.flir import cam
	elif cam_params["cameraMake"] == "emu":
		from campy.cameras.emu import cam
	else:
		print('Camera make is not supported by CamPy. Check config.')
	return cam

def LoadSystems(params):
	params["systems"] = {}
	cam_params = {}
	makes = GetMakeList(params)
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		cam = ImportCam(cam_params)
		params["systems"][makes[m]] = {}
		params["systems"][makes[m]]["system"] = cam.LoadSystem(params)
	return params

def LoadDevice(params, cam_params):
	cam = ImportCam(cam_params)
	cam_params = cam.LoadDevice(params, cam_params)
	return cam_params

def GetDeviceList(params):
	serials = []
	makes = GetMakeList(params)
	cam_params = {}
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		cam = ImportCam(cam_params)
		system = params["systems"][makes[m]]["system"]
		deviceList = cam.GetDeviceList(system)
		serials = []
		for i in range(len(deviceList)):
			serials.append(cam.GetSerialNumber(deviceList[i]))
		params["systems"][makes[m]]["serials"] = serials
		params["systems"][makes[m]]["deviceList"] = deviceList
	return params

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

def GrabFrames(cam_params, writeQueue, dispQueue, stopReadQueue, stopWriteQueue):
	# Import the cam module
	cam = ImportCam(cam_params)

	# Open the camera object
	camera, cam_params = cam.OpenCamera(cam_params)

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
				fps_count = round(frameNumber / (timeElapsed), 1)
				print('{} collected {} frames at {} fps for {} sec.'\
					.format(cam_params["cameraName"], frameNumber, fps_count, round(timeElapsed),1))

			cam.ReleaseFrame(grabResult)

			if stopReadQueue or frameNumber >= grabdata["numImagesToGrab"]:
				grabbing = False

		except Exception:
			time.sleep(0.001)

	# Close the camaera, save metadata, and tell writer and display to close
	cam.CloseCamera(cam_params, camera)
	SaveMetadata(cam_params, grabdata)
	if not sys.platform=='win32' or not cam_params['cameraMake'] == 'basler':
		dispQueue.append('STOP')
	stopWriteQueue.append('STOP')

def SaveMetadata(cam_params, grabdata):
	full_folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])

	try:
		# Zero timeStamps
		timeFirstGrab = grabdata["timeStamp"][0]
		grabdata["timeStamp"] = [i - timeFirstGrab for i in grabdata["timeStamp"]]

		# Get the frame and time counts to save into metadata
		frame_count = grabdata['frameNumber'][-1]
		time_count = grabdata['timeStamp'][-1]
		fps_count = int(round(frame_count/time_count))
		print('{} saved {} frames at {} fps.'.format(cam_params["cameraName"], frame_count, fps_count))

		meta = cam_params

		# Save frame data to numpy file
		npy_filename = os.path.join(full_folder_name, 'frametimes.npy')
		x = np.array([grabdata['frameNumber'], grabdata['timeStamp']])
		np.save(npy_filename,x)

		# Also save frame data to MATLAB file
		mat_filename = os.path.join(full_folder_name, 'frametimes.mat')
		matdata = {};
		matdata['frameNumber'] = grabdata['frameNumber']
		matdata['timeStamp'] = grabdata['timeStamp']
		sio.savemat(mat_filename, matdata, do_compression=True)

		# Save parameters and recording metadata to csv spreadsheet
		csv_filename = os.path.join(full_folder_name, 'metadata.csv')
		meta['totalFrames'] = grabdata['frameNumber'][-1]
		meta['totalTime'] = grabdata['timeStamp'][-1]
		
		with open(csv_filename, 'w', newline='') as f:
			w = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
			for row in meta.items():
				# Print items that are not objects or dicts
				if isinstance(row[1],(list,str,int,float)):
					w.writerow(row)

		print('Saved metadata for {}.'.format(cam_params['cameraName']))

	except Exception as e:
		logging.error('Caught exception: {}'.format(e))

def CloseSystems(params):
	print('Closing systems...')
	makes = GetMakeList(params)
	cam_params = {}
	for m in range(len(makes)):
		cam_params["cameraMake"] = makes[m]
		system = params["systems"][makes[m]]["system"]
		device_list = params["systems"][makes[m]]["deviceList"]
		cam = ImportCam(cam_params)
		cam.CloseSystem(system, device_list)
	print('Exiting campy...')
