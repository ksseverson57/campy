"""

"""

import PySpin
from campy.cameras import unicam
import os
import time
import logging
import sys
import numpy as np
from collections import deque
import csv

os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"

class TriggerType:
	SOFTWARE = 1
	HARDWARE = 2

CHOSEN_TRIGGER = TriggerType.HARDWARE

def ConfigureTrigger(camera):
	"""
	This function configures the camera to use a trigger. First, trigger mode is
	ensured to be off in order to select the trigger source. Trigger mode is
	then enabled, which has the camera capture only a single image upon the
	execution of the chosen trigger.
	 :param cam: Camera to configure trigger for.
	 :type cam: CameraPtr
	 :return: True if successful, False otherwise.
	 :rtype: bool
	"""

	print('*** CONFIGURING TRIGGER ***\n')
	if CHOSEN_TRIGGER == TriggerType.SOFTWARE:
		print('Software trigger chosen...')
	elif CHOSEN_TRIGGER == TriggerType.HARDWARE:
		print('Hardware trigger chose...')

	try:
		result = True
		# Ensure trigger mode off
		# The trigger must be disabled in order to configure whether the source
		# is software or hardware.
		if camera.TriggerMode.GetAccessMode() != PySpin.RW:
			print('Unable to disable trigger mode (node retrieval). Aborting...')
			return False
		camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)
		print('Trigger mode disabled...')

		# Select trigger source
		# The trigger source must be set to hardware or software while trigger
		# mode is off.
		if camera.TriggerSource.GetAccessMode() != PySpin.RW:
			print('Unable to get trigger source (node retrieval). Aborting...')
			return False

		if CHOSEN_TRIGGER == TriggerType.SOFTWARE:
			camera.TriggerSource.SetValue(PySpin.TriggerSource_Software)
		elif CHOSEN_TRIGGER == TriggerType.HARDWARE:
			camera.TriggerSource.SetValue(PySpin.TriggerSource_Line3)

		# Turn trigger mode on
		# Once the appropriate trigger source has been set, turn trigger mode
		# on in order to retrieve images using the trigger.
		camera.TriggerMode.SetValue(PySpin.TriggerMode_On)
		print('Trigger mode turned back on...')

	except PySpin.SpinnakerException as ex:
		print('Error: %s' % ex)
		return False

	return result

def ConfigureCustomImageSettings(cam_params, nodemap):
	"""
	Configures a number of settings on the camera including offsets  X and Y, width,
	height, and pixel format. These settings must be applied before BeginAcquisition()
	is called; otherwise, they will be read only. Also, it is important to note that
	settings are applied immediately. This means if you plan to reduce the width and
	move the x offset accordingly, you need to apply such changes in the appropriate order.
	:param nodemap: GenICam nodemap.
	:type nodemap: INodeMap
	:return: True if successful, False otherwise.
	:rtype: bool
	"""
	print('\n*** CONFIGURING CUSTOM IMAGE SETTINGS *** \n')
	try:
		result = True
		width_to_set = cam_params["frameWidth"]
		height_to_set = cam_params["frameHeight"]

		# Set maximum width
		#
		# *** NOTES ***
		# Other nodes, such as those corresponding to image width and height,
		# might have an increment other than 1. In these cases, it can be
		# important to check that the desired value is a multiple of the
		# increment. However, as these values are being set to the maximum,
		# there is no reason to check against the increment.
		node_width = PySpin.CIntegerPtr(nodemap.GetNode('Width'))
		if PySpin.IsAvailable(node_width) and PySpin.IsWritable(node_width):
			# width_to_set = node_width.GetMax()
			width_to_set = cam_params["frameWidth"]
			node_width.SetValue(width_to_set)
			print('Width set to %i...' % node_width.GetValue())
		else:
			 print('Width not available...')

		# Set maximum height
		# *** NOTES ***
		# A maximum is retrieved with the method GetMax(). A node's minimum and
		# maximum should always be a multiple of its increment.
		node_height = PySpin.CIntegerPtr(nodemap.GetNode('Height'))
		if PySpin.IsAvailable(node_height) and PySpin.IsWritable(node_height):
			# height_to_set = node_height.GetMax()
			height_to_set = cam_params["frameHeight"]
			node_height.SetValue(height_to_set)
			print('Height set to %i...' % node_height.GetValue())
		else:
			print('Height not available...')

	except PySpin.SpinnakerException as ex:
		print('Error: %s' % ex)
		return False

	return result, width_to_set, height_to_set

def PrintDeviceInfo(nodemap, cam_num):
	"""
	This function prints the device information of the camera from the transport
	layer; please see NodeMapInfo example for more in-depth comments on printing
	device information from the nodemap.
	:param nodemap: Transport layer device nodemap.
	:param cam_num: Camera number.
	:type nodemap: INodeMap
	:type cam_num: int
	:returns: True if successful, False otherwise.
	:rtype: bool
	"""

	print('Printing device information for camera %d... \n' % cam_num)
	try:
		result = True
		node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))
		if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
			features = node_device_information.GetFeatures()
			for feature in features:
				node_feature = PySpin.CValuePtr(feature)
				try:
					print('%s: %s' % (node_feature.GetName(), node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))
				except:
					pass
		else:
			print('Device control information not available.')
		print()
		return result
	except PySpin.SpinnakerException as ex:
		print('Error: %s' % ex)
		return False
	return result

def LoadSystem(params):

	return PySpin.System.GetInstance()

def GetDeviceList(system):

	return system.GetCameras()

def LoadDevice(cam_params, system, device_list):

	return device_list.GetByIndex(cam_params["cameraSelection"])

def GetSerialNumber(device):
	node_device_serial_number = PySpin.CStringPtr(device.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
	if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
		device_serial_number = node_device_serial_number.GetValue()
	else:
		device_serial_number = []
	return device_serial_number

def OpenCamera(cam_params, camera):
	# Retrieve TL device nodemap
	nodemap_tldevice = camera.GetTLDeviceNodeMap()
	# Print device information
	PrintDeviceInfo(nodemap_tldevice, cam_params["cameraSelection"])

	# Initialize camera object
	camera.Init()

	# Set acquisition mode to continuous
	node_acquisition_mode = PySpin.CEnumerationPtr(camera.GetNodeMap().GetNode('AcquisitionMode'))
	if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
		print('Unable to set acquisition mode to continuous (node retrieval; camera %d). Aborting... \n' % i)
		return False
	node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
	if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(
			node_acquisition_mode_continuous):
		print('Unable to set acquisition mode to continuous (entry \'continuous\' retrieval %d). \
		Aborting... \n' % i)
		return False
	acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()
	node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

	# Configure trigger
	trigConfig = ConfigureTrigger(camera)
	cam_params["trigConfig"] = trigConfig

	# Configure custom image settings
	settingsConfig, frameWidth, frameHeight = ConfigureCustomImageSettings(cam_params,camera.GetNodeMap())
	cam_params["settingsConfig"] = settingsConfig
	cam_params["frameWidth"] = frameWidth
	cam_params["frameHeight"] = frameHeight

	print("Opened {}, serial#: {}".format(cam_params["cameraName"], cam_params["cameraSerialNo"]))
	return cam_params, camera

def GrabFrames(cam_params, device, writeQueue, dispQueue, stopQueue):
	# Open the camera object
	cam_params, camera = OpenCamera(cam_params, device)

	# Create dictionary for appending frame number and timestamp information
	grabdata = unicam.GrabData(cam_params)

	# Start grabbing frames
	grabbing = False
	if cam_params["trigConfig"] and cam_params["settingsConfig"]:
		camera.BeginAcquisition()
		print("{} ready to trigger.".format(cam_params["cameraName"]))
		grabbing = True

	cnt = 0
	while(grabbing):
		if stopQueue or cnt >= grabdata["numImagesToGrab"]:
			# CloseCamera(cam_params, system, cam_list, camera, grabdata)
			CloseCamera(cam_params, camera, grabdata)
			writeQueue.append('STOP')
			break
		try:
			# Grab image from camera buffer if available
			image_result = camera.GetNextImage()
			if not image_result.IsIncomplete():
				img = image_result.GetNDArray()

				# Append numpy array to writeQueue for writer to append to file
				writeQueue.append(img)

				# Append timeStamp and frameNumber of grabbed frame to grabdata
				cnt += 1
				grabdata["frameNumber"].append(cnt) # first frame = 1
				camera.TimestampLatch.Execute()
				grabtime = camera.TimestampLatchValue.GetValue()/1e9
				grabdata["timeStamp"].append(grabtime)

				# Send image result to display queue for display
				if cnt % grabdata["frameRatio"] == 0:
					img = image_result.Convert(PySpin.PixelFormat_RGB8, PySpin.HQ_LINEAR).GetNDArray()
					dispQueue.append(img[::grabdata["ds"],::grabdata["ds"]])

				# Print number of frames collected after a user-defined chunk of time
				if cnt % grabdata["chunkLengthInFrames"] == 0:
					fps_count = int(round(cnt/grabtime - grabdata["timeStamp"][0]))
					print('{} collected {} frames at {} fps.' \
						.format(cam_params["cameraName"], cnt, fps_count))
			else:
				print('Image incomplete with image status {} ...'.format(image_result.GetImageStatus()))

			# Release grab object
			image_result.Release()

		# Else wait for next frame available
		except PySpin.SpinnakerException as ex:
			print('Error: %s' % ex)
			result = False
		except Exception as e:
			logging.error('Caught exception: {}'.format(e))

def CloseCamera(cam_params, camera, grabdata):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Close camera after acquisition stops
	while(True):
		try:
			try:
				unicam.SaveMetadata(cam_params,grabdata)
				time.sleep(0.5)

				# Close camera
				camera.EndAcquisition()
				camera.DeInit()
				del camera
				break
			except Exception as e:
				logging.error('Caught exception: {}'.format(e))
				break
		except KeyboardInterrupt:
			break

def CloseSystem(system, device_list):
	device_list.Clear()
	system.ReleaseInstance()
