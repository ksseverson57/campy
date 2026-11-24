"""
Unicam unifies camera APIs with common syntax to simplify multi-camera acquisition and 
reduce redundancy in campy code.
"""

import os, sys, time, csv, logging
import numpy as np
from collections import deque
from scipy import io as sio
from campy.utils.utils import Say
from campy import startup, statusline


def ImportCam(make):
	if make == "basler":
		from campy.cameras import basler as cam
	elif make == "flir":
		from campy.cameras import flir as cam
	elif make == "emu":
		from campy.cameras import emu as cam
	else:
		Say('Camera make is not supported by CamPy. Check config.')
	return cam


def LoadSystems(params):
	try:
		systems = {}
		makes = GetMakeList(params)
		for m in range(len(makes)):
			systems[makes[m]] = {}
			cam = ImportCam(makes[m])
			systems[makes[m]]["system"] = cam.LoadSystem(params)
	except Exception as e:
		logging.error('Caught exception at camera/unicam.py LoadSystems. Check cameraMake: {}'.format(e))
		raise
	return systems


def LoadDevice(systems, params, cam_params):
	try:
		cam = ImportCam(cam_params["cameraMake"])
		cam_params = cam.LoadDevice(systems, params, cam_params)
	except Exception as e:
		logging.error('Caught exception at camera/unicam.py LoadSystems. Check cameraMake: {}'.format(e))
		raise
	return cam_params


def OpenCamera(cam_params, stopWriteQueue):
	# Import the cam module
	cam = ImportCam(cam_params["cameraMake"])

	# With consoleSummary, what it says as it opens is one line once it is ready (campy/startup.py)
	startup.Begin(cam_params)
	try:
		camera, cam_params = cam.OpenCamera(cam_params)

		startup.Step("Opened {}: {} {} serial# {}".format( \
			cam_params["cameraName"],
			cam_params["cameraMake"], 
			cam_params["cameraModel"],
			cam_params["cameraSerialNo"]))

	except Exception as e:
		logging.error("Caught error at cameras/unicam.py OpenCamera: {}".format(e))
		stopWriteQueue.append('STOP')

	return cam, camera, cam_params


def GetDeviceList(systems, params):
	makes = GetMakeList(params)
	for m in range(len(makes)):
		cam = ImportCam(makes[m])
		system = systems[makes[m]]["system"]
		deviceList = cam.GetDeviceList(system)
		serials = [cam.GetSerialNumber(deviceList[i]) for i in range(len(deviceList))]
		systems[makes[m]]["serials"] = serials
		systems[makes[m]]["deviceList"] = deviceList
	return systems


def GetMakeList(params):
	if type(params["cameraMake"]) is list:
		cameraMakes = [params["cameraMake"][m] for m in range(len(params["cameraMake"]))]
	elif type(params["cameraMake"]) is str:
		cameraMakes = [params["cameraMake"]]
	makes = list(set(cameraMakes))
	return makes


def GrabData(cam_params):
	grabdata = {}
	grabdata["timeStamp"] = []
	grabdata["frameNumber"] = []
	grabdata["cameraName"] = cam_params["cameraName"]

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


def StartGrabbing(camera, cam_params, cam):
	grabbing = cam.StartGrabbing(camera)
	if grabbing:
		startup.Ready(cam_params)
	else:
		startup.Failed("it did not start grabbing")
	return grabbing


def CountFPS(grabdata, frameNumber, timeStamp):
	# With statusLine shown, the main process's status line says this instead
	if frameNumber % grabdata["chunkLengthInFrames"] == 0 and not statusline.Shown():
		timeElapsed = timeStamp - grabdata["timeStamp"][0]
		fpsCount = round((frameNumber - 1) / timeElapsed, 1)
		Say('{} collected {} frames at {} fps for {} sec.'\
			.format(grabdata["cameraName"], frameNumber, fpsCount, round(timeElapsed)))


def GrabFrames(cam_params, writeQueue, dispQueue, stopReadQueue, stopWriteQueue):
	# Open the camera object
	cam, camera, cam_params = OpenCamera(cam_params, stopWriteQueue)

	# Use Basler's default display window on Windows. Not supported on Linux
	if sys.platform=='win32' and cam_params["cameraMake"] == 'basler':
		dispQueue = cam.OpenPylonImageWindow(cam_params)

	# Create dictionary for appending frame number and timestamp information
	grabdata = GrabData(cam_params)

	# Start grabbing frames from the camera
	grabbing = StartGrabbing(camera, cam_params, cam)
	if grabbing:
		statusline.State(cam_params["n_cam"], statusline.GRABBING)

	frameNumber = 0
	while(not stopReadQueue):
		try:
			# Grab image from camera buffer if available
			grabResult = cam.GrabFrame(camera, frameNumber)

			# Append numpy array to writeQueue for writer to append to file
			img = cam.GetImageArray(grabResult)
			writeQueue.append(img)

			# Append timeStamp and frameNumber to grabdata
			frameNumber += 1
			grabdata['frameNumber'].append(frameNumber) # first frame = 1
			timeStamp = cam.GetTimeStamp(grabResult)
			grabdata['timeStamp'].append(timeStamp)
			statusline.Count(cam_params["n_cam"], frameNumber)

			# Display converted, downsampled image in the Window
			if frameNumber % grabdata["frameRatio"] == 0:
				img = cam.DisplayImage(cam_params, dispQueue, grabResult)

			CountFPS(grabdata, frameNumber, timeStamp)

			cam.ReleaseFrame(grabResult)

			if frameNumber >= grabdata["numImagesToGrab"]:
				break

		except Exception as e:
			if cam_params["cameraDebug"]:
				logging.error('Caught exception at cameras/unicam.py GrabFrames: {}'.format(e))
			time.sleep(0.001)

	# Close the camaera, save metadata, and tell writer and display to close
	statusline.State(cam_params["n_cam"], statusline.ENDED)
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
		startup.Saved(cam_params, frame_count, fps_count)

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

		startup.MetadataSaved(cam_params)

	except Exception as e:
		logging.error('Caught exception: {}'.format(e))


def CloseSystems(systems, params):
	Say('Closing systems...')
	makes = GetMakeList(params)
	for m in range(len(makes)):
		cam = ImportCam(makes[m])
		cam.CloseSystem(systems[makes[m]]["system"], systems[makes[m]]["deviceList"])
	Say('Exiting campy...')
