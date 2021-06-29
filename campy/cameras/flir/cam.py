"""
"""
import PySpin
from campy.cameras import unicam
import os
import time
from timeout_decorator import timeout
import logging
import sys
import numpy as np
import csv

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

class TriggerType:
	SOFTWARE = 1
	HARDWARE = 2

CHOSEN_TRIGGER = TriggerType.HARDWARE

def ConfigureTrigger(cam_params, camera):
	result = True
	try:
		camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)

		# Select trigger source
		if camera.TriggerSource.GetAccessMode() != PySpin.RW:
			print('Unable to get trigger source (node retrieval). Aborting...')

		if CHOSEN_TRIGGER == TriggerType.SOFTWARE:
			camera.TriggerSource.SetValue(PySpin.TriggerSource_Software)
		elif CHOSEN_TRIGGER == TriggerType.HARDWARE:
			eval('camera.TriggerSource.SetValue(PySpin.TriggerSource_%s)' % cam_params['cameraTrigger'])

		# Turn trigger mode on
		# Once the appropriate trigger source has been set, turn trigger mode
		# on in order to retrieve images using the trigger.
		camera.TriggerMode.SetValue(PySpin.TriggerMode_On)

		# Set Exposure active signal
		try:
			camera.LineSelector.SetValue(cam_params['cameraOut'])
			camera.LineMode.SetValue(True)
			camera.LineInverter.SetValue(True)
		except Exception as e:
			print('LineSelector')
			logging.error('Caught exception: {}'.format(e))

	except PySpin.SpinnakerException as ex:
		print('Error: %s' % ex)
		result = False

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

def PrintDeviceInfo(nodemap):
	try:
		node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))
		if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
			features = node_device_information.GetFeatures()
			for feature in features:
				node_feature = PySpin.CValuePtr(feature)
				try:
					print('%s: %s' % (node_feature.GetName(), node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))
				except Exception:
					pass
		else:
			print('Device control information not available.')
	except PySpin.SpinnakerException as ex:
		print('Error: %s' % ex)

def LoadSystem(params):

	return PySpin.System.GetInstance()

def GetDeviceList(system):

	return system.GetCameras()

def LoadDevice(params, cam_params):
	# device = device_list.GetByIndex(0) #cam_params["cameraSelection"]
	cam_params["camera"] = cam_params["device"]
	return cam_params

def GetSerialNumber(device):
	node_device_serial_number = PySpin.CStringPtr(device.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
	if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
		device_serial_number = node_device_serial_number.GetValue()
	else:
		device_serial_number = []
	return device_serial_number

def OpenCamera(cam_params):
	# Load camera
	camera = cam_params["camera"]

	# Retrieve TL device nodemap
	nodemap_tldevice = camera.GetTLDeviceNodeMap()

	# Print device information
	# PrintDeviceInfo(nodemap_tldevice)

	# Initialize camera object
	camera.Init()

	# Load camera settings
	cam_params = LoadSettings(cam_params, camera)

	print("Opened {}, serial#: {}".format(cam_params["cameraName"], cam_params["cameraSerialNo"]))
	return camera, cam_params

def LoadSettings(cam_params, camera):

	# Load default settings
	camera.UserSetSelector.SetValue(PySpin.UserSetSelector_Default)
	camera.UserSetLoad()

	# Set acquisition mode to continuous
	try:
		camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
	except Exception as e:
		print('AcquisitionMode')
		logging.error('Caught exception: {}'.format(e))

	# Configure trigger
	trigConfig = ConfigureTrigger(cam_params, camera)

	# Set exposure
	camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
	camera.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
	try:
		camera.ExposureTime.SetValue(cam_params["cameraExposureTimeInMs"])
	except Exception as e:
		print('Exposure')
		logging.error('Caught exception: {}'.format(e))

	# Set gain, gamma, and color balance
	camera.Gamma.SetValue(int(1))
	camera.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Off)
	camera.GainAuto.SetValue(PySpin.GainAuto_Off)
	try:
		camera.Gain.SetValue(cam_params["cameraGain"])
	except Exception as e:
		print('Gain')
		logging.error('Caught exception: {}'.format(e))

	# Configure custom image settings
	try:
		node_width = PySpin.CIntegerPtr(camera.GetNodeMap().GetNode('Width'))
		max_width = node_width.GetMax()
		if PySpin.IsAvailable(node_width) and PySpin.IsWritable(node_width):
			node_width.SetValue(cam_params["frameWidth"])

		node_height = PySpin.CIntegerPtr(camera.GetNodeMap().GetNode('Height'))
		max_height = node_height.GetMax()
		if PySpin.IsAvailable(node_height) and PySpin.IsWritable(node_height):
			node_height.SetValue(cam_params["frameHeight"])
	except Exception as e:
		print('Frame Height/Width: ({},{})'.format(node_width,node_height))
		logging.error('Caught exception: {}'.format(e))

	cam_params["frameWidth"] = node_width.GetValue()
	cam_params["frameHeight"] = node_height.GetValue()

	# Center X and Y offsets
	try:
		offsetX = int((max_width-cam_params["frameWidth"])/2)
		offsetY = int((max_height-cam_params["frameHeight"])/2)
		camera.OffsetX.SetValue(offsetX)
		camera.OffsetY.SetValue(offsetY)
	except Exception as e:
		print('Offset: ({},{})'.format(offsetX,offsetY))
		logging.error('Caught exception: {}'.format(e))	

	# Set bit depth and pixel format
	try:
		camera.PixelFormat.SetValue(PySpin.PixelFormat_BayerRG8)
	except Exception as e:
		print('PixelFormat')
		logging.error('Caught exception: {}'.format(e))	

	try:
		camera.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit10)
	except Exception as e:
		print('BitDepth')
		logging.error('Caught exception: {}'.format(e))

	return cam_params

def StartGrabbing(camera):
	try:
		camera.BeginAcquisition()
		return True
	except:
		return False

@timeout(5,use_signals=False) #timeout_exception=StopIteration,
def GrabFrame(camera, frameNumber):
	grabResult = camera.GetNextImage()
	return grabResult

def GetImageArray(grabResult, cam_params):

	return grabResult.GetNDArray()

def GetTimeStamp(grabResult, camera):
	camera.TimestampLatch.Execute()
	return camera.TimestampLatchValue.GetValue()*1e-9

def DisplayImage(cam_params, dispQueue, grabResult):
	# Convert to RGB
	img_converted = grabResult.Convert(PySpin.PixelFormat_RGB8, PySpin.HQ_LINEAR)

	# Get Numpy Array
	img = img_converted.GetNDArray()

	# Downsample image
	img = img[::cam_params["displayDownsample"],::cam_params["displayDownsample"]]

	# Send to display queue
	dispQueue.append(img)

def ReleaseFrame(grabResult):

	grabResult.Release()

def CloseCamera(cam_params, camera):
	print('Closing {}... Please wait.'.format(cam_params["cameraName"]))
	# Stop acquisition and close camera
	camera.EndAcquisition()
	camera.DeInit()

def CloseSystem(system, device_list):
	device_list.Clear()
	del device_list
	system.ReleaseInstance()
