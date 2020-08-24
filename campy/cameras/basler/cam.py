
import pypylon.pylon as pylon
import pypylon.genicam as geni

import os
import time
import logging
import sys

import numpy as np
from collections import deque

import csv

def Open(cam_params, bufferSize=500, validation=False):

	n_cam = cam_params["n_cam"]

	# Open and load features for all cameras
	tlFactory = pylon.TlFactory.GetInstance()
	devices = tlFactory.EnumerateDevices()
	camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(devices[n_cam]))
	serial = devices[n_cam].GetSerialNumber()
	camera.Close()
	camera.StopGrabbing()
	camera.Open()
	pylon.FeaturePersistence.Load(cam_params['camSettings'], camera.GetNodeMap(), validation)

	cam_params['cameraSerialNo'] = serial
	cam_params['cameraModel'] = camera.GetDeviceInfo().GetModelName()
	cam_params['frameWidth'] = camera.Width.GetValue()
	cam_params['frameHeight'] = camera.Height.GetValue()

	# Start grabbing frames (OneByOne = first in, first out)
	camera.MaxNumBuffer = bufferSize

	print("Started camera", n_cam, "serial#", serial)

	return camera, cam_params

def GrabFrames(cam_params, camera, writeQueue, dispQueue, stopQueue):

	n_cam = cam_params["n_cam"]

	cnt = 0
	timeout = 0

	# Create dictionary for appending frame number and timestamp information
	grabdata = {}
	grabdata['timeStamp'] = []
	grabdata['frameNumber'] = []

	frameRate = cam_params['frameRate']
	recTimeInSec = cam_params['recTimeInSec']
	chunkLengthInSec = cam_params["chunkLengthInSec"]
	ds = cam_params["displayDownsample"]
	displayFrameRate = cam_params["displayFrameRate"]

	frameRatio = int(round(frameRate/displayFrameRate))
	numImagesToGrab = recTimeInSec*frameRate
	chunkLengthInFrames = int(round(chunkLengthInSec*frameRate))

	if sys.platform=='win32' and cam_params['cameraMake'] == 'basler':
		imageWindow = pylon.PylonImageWindow()
		imageWindow.Create(n_cam)
		imageWindow.Show()

	camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
	print("Camera", str(n_cam+1), "ready to trigger.")

	while(camera.IsGrabbing()):
		if stopQueue or cnt >= numImagesToGrab:
			close_camera(cam_params, camera, grabdata)
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
					dispQueue.append(grabResult.Array[::ds,::ds])

			grabResult.Release()

			if cnt % chunkLengthInFrames == 0:
				fps_count = int(round(cnt/grabtime))
				print('Camera %i collected %i frames at %i fps.' % (n_cam,cnt,fps_count))

		# Else wait for next frame available
		except geni.GenericException:
			time.sleep(0.0001)

		except Exception as e:
			logging.error('Caught exception: {}'.format(e))

def close_camera(cam_params, camera, grabdata):

	n_cam = cam_params["n_cam"]

	print('Closing camera {}... Please wait.'.format(n_cam+1))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				save_metadata(cam_params,grabdata)
				time.sleep(1)
				camera.Close()
				camera.StopGrabbing()
				break
			except:
				time.sleep(0.1)
		except KeyboardInterrupt:
			break

def save_metadata(cam_params, grabdata):
	
	n_cam = cam_params["n_cam"]

	full_folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])

	meta = cam_params
	meta['timeStamp'] = grabdata['timeStamp']
	meta['frameNumber'] = grabdata['frameNumber']

	frame_count = meta['frameNumber'][-1]
	time_count = meta['timeStamp'][-1]
	fps_count = int(round(frame_count/time_count))
	print('Camera {} saved {} frames at {} fps.'.format(n_cam+1, frame_count, fps_count))

	try:
		npy_filename = os.path.join(full_folder_name, 'frametimes.npy')
		x = np.array([meta['frameNumber'], meta['timeStamp']])
		np.save(npy_filename,x)
	except:
		pass

	csv_filename = os.path.join(full_folder_name, 'metadata.csv')
	keys = meta.keys()
	vals = meta.values()
	
	try:
		with open(csv_filename, 'w', newline='') as f:
			w = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
			for row in meta.items():
				w.writerow(row)
	except:
		pass
