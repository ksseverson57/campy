import os
import numpy as np
import csv

def ImportCam(cam_params):
	if cam_params["cameraMake"] == "basler":
		from campy.cameras.basler import cam
	elif cam_params["cameraMake"] == "flir":
		from campy.cameras.flir import cam
	elif cam_params["cameraMake"] == "emu":
		from campy.cameras.emu import cam
	return cam

def GetDeviceList(params, systems):
	deviceSerials = []
	deviceSystems = []
	makeList = GetMakeList(params)
	cam_params = {}
	for c in range(len(makeList)):
		cam_params["cameraMake"] = makeList[c]
		cam = ImportCam(cam_params)
		deviceList = cam.GetDeviceList(systems[cam_params["cameraMake"]])
		numDevices = len(deviceList)
		for i in range(numDevices):
			deviceSerials.append(cam.GetSerialNumber(deviceList[i]))
			deviceSystems.append(cam_params["cameraMake"])
	return deviceList, deviceSerials

def GetMakeList(params):
	cameraMakes = []
	if type(params["cameraMake"]) is list:
		for c in range(len(params["cameraMake"])):
			cameraMakes.append(params["cameraMake"][c])
	elif type(params["cameraMake"]) is str:
		cameraMakes.append(params["cameraMake"])
	makeList = list(set(cameraMakes))
	return makeList

def LoadDevice(cam_params, systems):
	system = systems[cam_params["cameraMake"]]
	device_list = systems["deviceList"]
	cam = ImportCam(cam_params)
	device = cam.LoadDevice(cam_params, system, device_list)
	return device

def LoadSystems(params):
	systems = {}
	makeList = GetMakeList(params)
	cam_params = {}
	for c in range(len(makeList)):
		cam_params["cameraMake"] = makeList[c]
		cam = ImportCam(cam_params)
		systems[cam_params["cameraMake"]] = cam.LoadSystem(params)
	return systems

def CloseSystems(params,systems):
	device_list = systems["deviceList"]
	makeList = GetMakeList(params)
	cam_params = {}
	for c in range(len(makeList)):
		cam_params["cameraMake"] = makeList[c]
		system = systems[cam_params["cameraMake"]]
		cam = ImportCam(cam_params)
		cam.CloseSystem(system, device_list)

def GrabData(cam_params):
	grabdata = {}
	grabdata["timeStamp"] = []
	grabdata["frameNumber"] = []
	grabdata["ds"] = cam_params["displayDownsample"]

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