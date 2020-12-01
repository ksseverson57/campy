"""

"""

import pypylon.pylon as pylon
import pypylon.genicam as geni
import os
import time
import logging
import sys
import numpy as np
from collections import deque
import csv

def OpenCamera(cam_params, bufferSize=500, validation=False):
	n_cam = cam_params["n_cam"]
	cam_index = cam_params["cameraSelection"]
	camera_name = cam_params["cameraName"]

	# Open and load features for all cameras
	tlFactory = pylon.TlFactory.GetInstance()
	devices = tlFactory.EnumerateDevices()
	camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(devices[cam_index]))
	serial = devices[cam_index].GetSerialNumber()
	camera.Close()
	camera.StopGrabbing()
	camera.Open()
	pylon.FeaturePersistence.Load(cam_params['cameraSettings'], camera.GetNodeMap(), validation)

	# Get camera information and save to cam_params for metadata
	cam_params['cameraSerialNo'] = serial
	cam_params['cameraModel'] = camera.GetDeviceInfo().GetModelName()

	# Set features manually or automatically, depending on configuration
	cam_params['frameWidth'] = camera.Width.GetValue()
	cam_params['frameHeight'] = camera.Height.GetValue()

	# Start grabbing frames (OneByOne = first in, first out)
	camera.MaxNumBuffer = bufferSize
	print("Started", camera_name, "serial#", serial)

	return camera, cam_params

def GrabFrames(cam_params, camera, writeQueue, dispQueue, stopQueue):
	n_cam = cam_params["n_cam"]

	cnt = 0
	timeout = 0

	# Create dictionary for appending frame number and timestamp information
	grabdata = {}
	grabdata['timeStamp'] = []
	grabdata['frameNumber'] = []

	numImagesToGrab = cam_params['recTimeInSec']*cam_params['frameRate']
	chunkLengthInFrames = int(round(cam_params["chunkLengthInSec"]*cam_params['frameRate']))

	if cam_params["displayFrameRate"] <= 0:
		frameRatio = float('inf')
	elif cam_params["displayFrameRate"] > 0 and cam_params["displayFrameRate"] <= cam_params['frameRate']:
		frameRatio = int(round(cam_params['frameRate']/cam_params["displayFrameRate"]))
	else:
		frameRatio = cam_params['frameRate']

	if sys.platform=='win32':
		imageWindow = pylon.PylonImageWindow()
		imageWindow.Create(n_cam)
		imageWindow.Show()

	camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
	print(cam_params["cameraName"], "ready to trigger.")

	while(camera.IsGrabbing()):
		if stopQueue or cnt >= numImagesToGrab:
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break
		try:
			# Grab image from camera buffer if available
			grabResult = camera.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)

			# Append numpy array to writeQueue for writer to append to file
			writeQueue.append(grabResult.Array)

			if cnt == 0:
				timeFirstGrab = grabResult.TimeStamp
			grabtime = (grabResult.TimeStamp - timeFirstGrab)/1e9
			grabdata['timeStamp'].append(grabtime)

			cnt += 1
			grabdata['frameNumber'].append(cnt) # first frame = 1

			if cnt % frameRatio == 0:
				if sys.platform == 'win32' and cam_params['cameraMake'] == 'basler':
					try:
						imageWindow.SetImage(grabResult)
						imageWindow.Show()
					except Exception as e:
						logging.error('Caught exception: {}'.format(e))
				else:
					dispQueue.append(grabResult.Array[::cam_params["displayDownsample"],
													::cam_params["displayDownsample"]])
			grabResult.Release()

			if cnt % chunkLengthInFrames == 0:
				fps_count = int(round(cnt/grabtime))
				print('Camera %i collected %i frames at %i fps.' % (n_cam,cnt,fps_count))
		# Else wait for next frame available
		except geni.GenericException:
			time.sleep(0.0001)
		except Exception as e:
			logging.error('Caught exception: {}'.format(e))

def CloseCamera(cam_params, camera, grabdata):
	n_cam = cam_params["n_cam"]

	print('Closing camera {}... Please wait.'.format(n_cam+1))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				SaveMetadata(cam_params,grabdata)
				time.sleep(1)
				camera.Close()
				camera.StopGrabbing()
				break
			except:
				time.sleep(0.1)
		except KeyboardInterrupt:
			break

def SaveMetadata(cam_params, grabdata):
	n_cam = cam_params["n_cam"]
	full_folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])

	# Save frame numbers and timestamps in numpy array
	frame_count = grabdata['frameNumber'][-1]
	time_count = grabdata['timeStamp'][-1]
	fps_count = int(round(frame_count/time_count))
	print('Camera {} saved {} frames at {} fps.'.format(n_cam+1, frame_count, fps_count))
	try:
		npy_filename = os.path.join(full_folder_name, 'frametimes.npy')
		x = np.array([grabdata['frameNumber'], grabdata['timeStamp']])
		np.save(npy_filename,x)
	except:
		pass

	# Save other recording metadata in csv file
	meta = cam_params
	meta['totalFrames'] = grabdata['frameNumber'][-1]
	meta['totalTime'] = grabdata['timeStamp'][-1]
	keys = meta.keys()
	vals = meta.values()
	
	csv_filename = os.path.join(full_folder_name, 'metadata.csv')
	try:
		with open(csv_filename, 'w', newline='') as f:
			w = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
			for row in meta.items():
				w.writerow(row)
	except:
		pass
