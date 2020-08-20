
import pypylon.pylon as pylon
import pypylon.genicam as geni

import os
import time
import logging
import sys

import numpy as np
from collections import deque

import csv

def Open(c, camSettings, meta, bufferSize=500, validation=True):

	# Open and load features for all cameras
	tlFactory = pylon.TlFactory.GetInstance()
	devices = tlFactory.EnumerateDevices()
	camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(devices[c]))
	serial = devices[c].GetSerialNumber()
	camera.Close()
	camera.StopGrabbing()
	camera.Open()
	pylon.FeaturePersistence.Load(camSettings, camera.GetNodeMap(), validation)

	meta['CameraSerialNo'] = serial
	meta['CameraModel'] = camera.GetDeviceInfo().GetModelName()
	meta['FrameWidth'] = camera.Width.GetValue()
	meta['FrameHeight'] = camera.Height.GetValue()

	# Start grabbing frames (OneByOne = first in, first out)
	camera.MaxNumBuffer = bufferSize

	print("Started camera", c, "serial#", serial)

	return camera, meta

def GrabFrames(c, camera, meta, videoFolder, writeQueue, 
				dispQueue, displayFrameRate=10, displayDownSample=2):
	
	chunkSizeInSec = 30
	cnt = 0
	timeout = 0

	# Create dictionary for appending frame number and timestamp information
	grabdata = {}
	grabdata['TimeStamp'] = []
	grabdata['FrameNumber'] = []

	frameRate = meta['FrameRate']
	recTimeInSec = meta['RecordingSetDuration']

	frameRatio = int(round(frameRate/displayFrameRate))
	ds = displayDownSample

	numImagesToGrab = recTimeInSec*frameRate
	chunkSizeInFrames = int(round(chunkSizeInSec*frameRate))

	if sys.platform=='win32':
		imageWindow = pylon.PylonImageWindow()
		imageWindow.Create(c)
		imageWindow.Show()
	elif sys.platform == 'linux' or sys.platform == 'linux2':
		figure, imageWindow = draw_figure(c+1) 

	camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
	print("Camera", c, "ready to trigger.")

	while(camera.IsGrabbing()):
		try:
			if cnt >= numImagesToGrab:
				writeQueue.append('STOP')
				Close(c,camera)
				SaveMetadata(c,meta,grabdata,videoFolder)
				camera.StopGrabbing()
				if sys.platform == 'linux' or sys.platform == 'linux2':
					plt.close(figure)
				break

			try:
				# Grab image from camera buffer if available
				grabResult = camera.RetrieveResult(timeout, pylon.TimeoutHandling_ThrowException)

				# Append numpy array to writeQueue for writer to append to file
				writeQueue.append(grabResult.Array) # deque

				if cnt == 0:
					timeFirstGrab = grabResult.TimeStamp
				grabtime = (grabResult.TimeStamp - timeFirstGrab)/1e9
				grabdata['TimeStamp'].append(grabtime)

				cnt += 1
				grabdata['FrameNumber'].append(cnt) # first frame = 1

				if cnt % frameRatio == 0:
					if sys.platform == 'win32':
						try:
							# dispQueue.append(grabResult)
							imageWindow.SetImage(grabResult)
							imageWindow.Show()
						except Exception as e:
							logging.error('Caught exception: {}'.format(e))
					elif sys.platform == 'linux' or sys.platform == 'linux2':
						try:
							# dispQueue.append(grabResult.Array[::ds,::ds])
							imageWindow.set_data(img)
							figure.canvas.draw()
							figure.canvas.flush_events()
						except Exception as e:
							logging.error('Caught exception: {}'.format(e))

				grabResult.Release()

				if cnt % chunkSizeInFrames == 0:
					fps_count = int(round(cnt/grabtime))
					print('Camera %i collected %i frames at %i fps.' % (c,cnt,fps_count))

			# Else wait for next frame available
			except geni.GenericException:
				time.sleep(0.0001)

			except Exception as e:
				logging.error('Caught exception: {}'.format(e))

		except KeyboardInterrupt:
			try:
				writeQueue.append('STOP')
				Close(c, camera)
				SaveMetadata(c, meta, grabdata, videoFolder)
				camera.StopGrabbing()
				if sys.platform == 'linux' or sys.platform == 'linux2':
					plt.close(figure)
			except Exception as e:
				logging.error('Caught exception: {}'.format(e))
			break

def Close(c, camera):
	print('Closing camera {}... Please wait.'.format(c+1))
	# Close Basler camera after acquisition stops
	while(True):
		try:
			try:
				camera.Close()
				break
			except:
				time.sleep(0.1)
		except KeyboardInterrupt:
			break

def SaveMetadata(c, meta, grabdata, videoFolder):

	full_folder_name = os.path.join(videoFolder, 'Camera' + str(c+1))

	meta['TimeStamp'] = grabdata['TimeStamp']
	meta['FrameNumber'] = grabdata['FrameNumber']

	cnt = meta['FrameNumber'][-1]
	fps_count = str(int(round(cnt/meta['TimeStamp'][-1])))

	print('Camera {} saved {} frames at {} fps.'.format(c+1, cnt, fps_count))

	x = np.array([meta['FrameNumber'], meta['TimeStamp']])


	npy_filename = os.path.join(full_folder_name, 'metadata.npy')
	np.save(npy_filename,x)

	csv_filename = os.path.join(full_folder_name, 'metadata.csv')
	keys = meta.keys()
	vals = meta.values()
	
	with open(csv_filename, 'w', newline='') as f:
		w = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
		for row in meta.items():
			w.writerow(row)
