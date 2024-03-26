"""
unicam is a translation layer that 
unifies camera APIs with common syntax 
to generalize multi-camera acquisition and 
reduce redundancy in campy.
"""

import os, sys, time, csv, logging
import numpy as np
from collections import deque
from scipy import io as sio
import datetime
from campy.trigger import trigger


def ImportCam(make):
	if make == "basler":
		from campy.cameras import basler as cam
	elif make == "flir":
		from campy.cameras import flir as cam
	elif make == "emu":
		from campy.cameras import emu as cam
	else:
		print('Camera make is not supported by CamPy. Check config.', flush=True)
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

	try:
		camera, cam_params = cam.OpenCamera(cam_params)

		print("Opened {}: {} {} serial# {}".format( \
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
		grabdata["frameRatio"] = int(round(cam_params["frameRate"] / cam_params["displayFrameRate"]))
	else:
		grabdata["frameRatio"] = cam_params["frameRate"]

	# Calculate number of images
	grabdata["numImagesToGrab"] = int(round(cam_params["recTimeInSec"] * cam_params["frameRate"]))
	grabdata["displayFrameCounter"] = int(round(cam_params["displayFrameCounter"] * cam_params["frameRate"]))

	return grabdata


def StartGrabbing(camera, cam_params, cam):

	return cam.StartGrabbing(camera)


def CountFPS(grabdata, frameNumber, timeElapsed):
	if frameNumber == grabdata["numImagesToGrab"]:
		# If last frame, clear output
		print("\r", end="")
	elif timeElapsed != 0 and frameNumber % grabdata["displayFrameCounter"] == 0:
		fpsCount = round((frameNumber) / timeElapsed, 1)
		print('Collected {} frames at {} fps for {} sec.'\
			.format(frameNumber, fpsCount, round(timeElapsed, 1)),
			end="\r")


def PackDictionary(img, frameNumber, timestamp):
	im_dict = dict()
	im_dict["array"] = img
	im_dict["frameNumber"] = frameNumber
	im_dict["timestamp"] = timestamp

	return im_dict


def GrabFrames(
	cam_params, 
	writeQueue, 
	dispQueue, 
	stopGrabQueue, 
	stopReadQueue, 
	stopWriteQueue
):
	# Open the camera object
	cam, camera, cam_params = OpenCamera(cam_params, stopWriteQueue)

	# Create dictionary for appending frame number and timestamp information
	grabdata = GrabData(cam_params)

	# Start grabbing frames from the camera
	grabbing = StartGrabbing(camera, cam_params, cam)
	closing = False
	closed = False
	frameNumber = int(0)

	# If pixelformat is bayer, initialize bayer-RGB converter
	if cam_params["pixelFormatInput"].find("bayer") != -1:
		converter = cam.GetConverter()
	else:
		converter = None

	while(True):
		if stopGrabQueue or frameNumber >= grabdata["numImagesToGrab"]:
			# Get the recording end date and time
			if grabbing:
				# First send command to microcontroller to stop triggers
				if cam_params["startArduino"] and "triggers" in cam_params.keys():
					trigger.StopTriggers(cam_params["triggers"], cam_params)
					print("Closing serial connection...", flush=True)
				grabdata["dateTimeEnd"] = datetime.datetime.now()

			grabbing = False

		if grabbing:
			try:
				# Grab image from camera buffer if available
				grabResult = cam.GrabFrame(camera, frameNumber)

				if cam.GrabSucceeded(grabResult):

					# Append timeStamp and frameNumber to grabdata
					timeStamp = cam.GetTimeStamp(grabResult)

					# Get the recording start datetime and timestamp
					if frameNumber == 0:
						grabdata["dateTimeStart"] = datetime.datetime.now()
						grabdata["timeStart"] = timeStamp

					# Compute time elapsed and count fps
					timeElapsed = timeStamp - grabdata["timeStart"]
					CountFPS(grabdata, frameNumber, timeElapsed)

					# Queue copy of RGB image for display
					if frameNumber % grabdata["frameRatio"] == 0:
						cam.DisplayImage(cam_params, dispQueue, grabResult, converter)

					# Queue image array from grab result
					if cam_params["zeroCopy"]:
						# Use context manager to pass memory pointer for zero-copy 
						with cam.GetImageArray(grabResult) as img:
							im_dict = PackDictionary(img, frameNumber, timeElapsed)
							writeQueue.append(im_dict)
					else:
						img = cam.CopyImageArray(grabResult)
						im_dict = PackDictionary(img, frameNumber, timeElapsed)
						writeQueue.append(im_dict)
						cam.ReleaseFrame(grabResult)

					# Count current frame (first frame = 0)
					frameNumber = frameNumber + 1

				else:
					# Release grabbed frame object to free memory buffer **Test with 
					print('Grab failed for camera {}, frame {}'.format(cam_params["n_cam"] + 1, frameNumber))
					cam.ReleaseFrame(grabResult)

			except Exception as e:
				if cam_params["cameraDebug"]:
					logging.error('Caught exception at cameras/unicam.py GrabFrames: {}'.format(e))
				time.sleep(0.0001)
		else:
			# If frame grabbing is complete, initiate closing sequence
			if not closing:
				# Close the camera, save metadata, and tell writer and display to close
				CountFPS(grabdata, frameNumber, timeElapsed)
				grabdata["timeEnd"] = timeElapsed
				grabdata["frameNumber"] = frameNumber
				SaveMetadata(cam_params, grabdata)
				dispQueue.append("STOP")
				stopWriteQueue.append("STOP")
				closing = True
			else:
				if not closed:
					if stopReadQueue:
						cam.CloseCamera(cam_params, camera)
						closed = True
				else:
					time.sleep(0.01)


# Move timestamp saving to writer process/thread
def SaveMetadata(cam_params, grabdata):
	full_folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])

	try:
		# Get the frame and time counts to save into metadata
		frame_count = grabdata['frameNumber']
		time_count = grabdata['timeEnd']
		fps_count = round((frame_count - 1) / time_count, 3)
		print('{} grabbed {} frames at {} fps.'.format(cam_params["cameraName"], frame_count, fps_count))

		meta = cam_params

		# Save parameters and recording metadata to csv spreadsheet
		csv_filename = os.path.join(full_folder_name, 'metadata.csv')
		meta['totalFrames'] = int(grabdata['frameNumber'])
		meta['totalTime'] = grabdata['timeEnd']
		meta['dateStart'] = grabdata['dateTimeStart'].strftime("%Y/%m/%d")
		meta['dateEnd'] = grabdata['dateTimeEnd'].strftime("%Y/%m/%d")
		meta['timeStart'] = grabdata['dateTimeStart'].strftime("%H:%M:%S") # :%f # microseconds
		meta['timeEnd'] = grabdata['dateTimeEnd'].strftime("%H:%M:%S")

		with open(csv_filename, 'w', newline='') as f:
			w = csv.writer(f, delimiter=',', quoting=csv.QUOTE_ALL)
			for row in meta.items():
				# Print items that are not objects or dicts
				if isinstance(row[1],(list,str,int,float)):
					w.writerow(row)

		print("Recording for {} ended on {} at {}".format(
			cam_params['cameraName'], 
			meta['dateEnd'], 
			meta['timeEnd']))

	except Exception as e:
		logging.error('Caught exception: {}'.format(e))


def CloseSystems(systems, params):
	print('Closing systems...')
	makes = GetMakeList(params)
	for m in range(len(makes)):
		cam = ImportCam(makes[m])
		cam.CloseSystem(systems[makes[m]]["system"], systems[makes[m]]["deviceList"])
	print('Exiting campy...')
