"""

"""

import os
import time
import logging
import sys
import numpy as np
from collections import deque
import csv
import imageio

def OpenCamera(cam_params, bufferSize=500, validation=False):
	n_cam = cam_params["n_cam"]
	cam_index = cam_params["cameraSelection"]
	camera_name = cam_params["cameraName"]

	# Open video reader for emulation
	full_file_name = os.path.join(cam_params["videoFolder"],cam_params["cameraName"],cam_params["videoFilename"])
	camera = imageio.get_reader(full_file_name)

	# Set features manually or automatically, depending on configuration
	frame_size = camera.get_meta_data()['size']
	cam_params['frameWidth'] = frame_size[0]
	cam_params['frameHeight'] = frame_size[1]

	# Start grabbing frames (OneByOne = first in, first out)
	camera.MaxNumBuffer = bufferSize
	print("Started", camera_name, "emulation.")
	return camera, cam_params

def GrabFrames(cam_params, camera, writeQueue, dispQueue, stopQueue):
	n_cam = cam_params["n_cam"]

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
	print(cam_params["cameraName"], "ready to emulate.")

	cnt = 0
	while(True):
		if stopQueue or cnt >= numImagesToGrab:
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break
		try:
			timeStart = time.perf_counter()
			# Grab image from camera buffer if available
			grabResult = camera.get_data(cnt)

			# Append numpy array to writeQueue for writer to append to file
			writeQueue.append(grabResult)

			if cnt == 0:
				timeFirstGrab = time.perf_counter()
			grabtime = (time.perf_counter() - timeFirstGrab)
			grabdata['timeStamp'].append(grabtime)

			cnt += 1
			grabdata['frameNumber'].append(cnt) # first frame = 1

			if cnt % frameRatio == 0:
				dispQueue.append(grabResult[::cam_params["displayDownsample"],
											::cam_params["displayDownsample"],
											:])
			if cnt % chunkLengthInFrames == 0:
				fps_count = int(round(cnt/grabtime))
				print('Camera %i collected %i frames at %i fps.' % (n_cam,cnt,fps_count))

			# Waits until frame time has been reached to fix frame rate
			while(time.perf_counter()-timeStart < 1/cam_params["frameRate"]):
				pass

		except Exception as e:
			logging.error('Caught exception in grabFrames: {}'.format(e))
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break

def CloseCamera(cam_params, camera, grabdata):
	n_cam = cam_params["n_cam"]

	print('Closing camera {}... Please wait.'.format(n_cam+1))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				SaveMetadata(cam_params,grabdata)
				time.sleep(1)
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
