"""
"""
import PySpin
from campy.cameras import unicam
import os, sys, time, logging
import numpy as np
import cv2


os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class ImageNotCompleteException(Exception):
	"""Exception raised for errors in the input.
	Attributes:
		expression -- input expression in which the error occurred
		message -- explanation of the error
	"""

	def __init__(self, expression, message):
		self.expression = expression
		self.message = message


def LoadSystem(params):

	return PySpin.System.GetInstance()


def GetDeviceList(system):

	return system.GetCameras()


def LoadDevice(systems, params, cam_params):
	cam_params["camera"] = cam_params["device"]
	return cam_params


def GetSerialNumber(device):
	node_device_serial_number = PySpin.CStringPtr(device.GetTLDeviceNodeMap().GetNode("DeviceSerialNumber"))
	if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
		device_serial_number = node_device_serial_number.GetValue()
	else:
		device_serial_number = []

	return device_serial_number


def GetModelName(camera):
	node_device_model_name = PySpin.CStringPtr(camera.GetTLDeviceNodeMap().GetNode("DeviceModelName"))
	if PySpin.IsAvailable(node_device_model_name) and PySpin.IsReadable(node_device_model_name):
		device_model_name = node_device_model_name.GetValue()
	else:
		device_model_name = []

	return device_model_name


def OpenCamera(cam_params):

	# Load camera
	camera = cam_params["camera"]

	# Initialize camera object
	camera.Init()

	# Reset to factory default settings
	camera.UserSetSelector.SetValue(PySpin.UserSetSelector_Default)
	camera.UserSetLoad()

	# Retrieve TL device nodemap
	nodemap_tldevice = camera.GetTLDeviceNodeMap()

	# Print device information
	PrintDeviceInfo(nodemap_tldevice, cam_params)
	cam_params['cameraModel'] = GetModelName(camera)

	# Load camera settings
	cam_params = LoadSettings(camera, cam_params)

	return camera, cam_params


def LoadSettings(camera, cam_params):

	try:
		# Configure trigger
		cam_params = ConfigureTrigger(camera, cam_params)

		# Configure custom image settings (acquisition, white balance, frame height/width/offsets, 
		# pixel format, exposure, gain, gamma, buffer and chunkdata mode (e.g. timestamp/frame info))
		cam_params = ConfigureCustomImageSettings(camera, cam_params)

	except Exception as e:
		logging.error("Caught error at cameras/flir.py LoadSettings: {}".format(e))

	return cam_params


def StartGrabbing(camera):
	try:
		camera.BeginAcquisition()
		return True
	except PySpin.SpinnakerException as e:
		print("Error: {}".format(e))
		return False
	except Exception as e:
		print("Exception in cameras/flir.py function StartGrabbing(camera): {}".foramt(e))
		return False


def GrabFrame(camera, frameNumber):
	image_result = camera.GetNextImage()

	#  Ensure image completion
	if image_result.IsIncomplete():
		image_status = image_result.GetImageStatus()
		print("Image incomplete with image status %d ..." % image_status)
		raise ImageNotCompleteException("Image not complete", image_status)

	return image_result


def GetImageArray(grabResult):

	return grabResult.GetNDArray()


def CopyImageArray(grabResult):

	return grabResult.GetNDArray()


def GetTimeStamp(grabResult):

	return grabResult.GetChunkData().GetTimestamp() * 1e-9


def GetFrameID(chunkData):

	return chunkData.GetFrameID()


def DisplayImage(cam_params, dispQueue, grabResult, converter=None): 
	try:
		# Convert color to RGB for display in opencv
		if str(converter) == "None":
			# Convert to Numpy array
			img = GetImageArray(grabResult)

			# Use OpenCV color converter For older PySpin versions (<2.7)
			if cam_params["pixelFormatInput"] == "bayer_rggb8":
				img = cv2.cvtColor(img, cv2.COLOR_BAYER_RG2RGB)
			elif cam_params["pixelFormatInput"] == "bayer_bggr8":
				img = cv2.cvtColor(img, cv2.COLOR_BAYER_BG2RGB)
			elif cam_params["pixelFormatInput"] == "gray":
				img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
		else:
			img = ConvertBayerToRGB(converter, grabResult)

		# Downsample image
		img = img[::cam_params["displayDownsample"], ::cam_params["displayDownsample"]]

		# Send to display queue
		dispQueue.append(img)

	except Exception as e:
		logging.error('Caught exception at cameras/flir.py DisplayImage: {}.'.format(e))


def ReleaseFrame(grabResult):

	grabResult.Release()


def CloseCamera(cam_params, camera):
	print("Closing {}... Please wait.".format(cam_params["cameraName"]))
	# Close camera after acquisition stops
	while True:
		try:
			try:
				# Close camera
				camera.EndAcquisition()
				camera.DeInit()
				del camera
				break
			except PySpin.SpinnakerException as e:
				print("Error: {}".format(e))
				raise
			except Exception as e:
				logging.error("Caught exception at cameras/flir.py CloseCamera: {}".format(e))
				raise
				break
		except KeyboardInterrupt:
			break


def CloseSystem(system, device_list):
	try:
		device_list.Clear()
		system.ReleaseInstance()
	except PySpin.SpinnakerException as e:
		print("SpinnakerException at cameras/flir.py CloseSystem: {}".format(e))
		print("passing from", __name__)
		raise
	except Exception as e:
		print("Exception at cameras/flir.py CloseSystem: {}".format(e))
		raise


# Flir-Specific Functions
def ConfigureCustomImageSettings(camera, cam_params):
	"""
	Configures a number of settings on the camera including offsets X and Y, width,
	height, and pixel format. These settings must be applied before BeginAcquisition()
	is called; otherwise, they will be read only. Also, it is important to note that
	settings are applied immediately. This means if you plan to reduce the width and
	move the x offset accordingly, you need to apply such changes in the appropriate order.
	:param nodemap: GenICam nodemap.
	:type nodemap: INodeMap
	:return: True if successful, False otherwise.
	:rtype: bool
	"""

	try:
		if cam_params["cameraDebug"]:
			print("\n*** CONFIGURING CUSTOM IMAGE SETTINGS *** \n")

		settingsConfig = True

		camera.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)
		camera.BalanceWhiteAuto.SetValue(PySpin.BalanceWhiteAuto_Off)

		cam_params = ConfigureFrameWidth(camera, cam_params)
		cam_params = ConfigureFrameHeight(camera, cam_params)
		cam_params = ConfigurePixelFormat(camera, cam_params)
		cam_params = ConfigureExposure(camera, cam_params)
		cam_params = ConfigureGain(camera, cam_params)
		cam_params = ConfigureGamma(camera, cam_params)
		cam_params = ConfigureBuffer(camera, cam_params)
		cam_params = ConfigureChunkData(camera, cam_params)

	except Exception as e:
		logging.error("Caught error at cameras/flir.py ConfigureCustomImageSettings: {}".format(e))
		settingsConfig = False

	cam_params["settingsConfig"] = settingsConfig

	return cam_params


def ConfigureBuffer(camera, cam_params):
	"""
	This function configures the camera's frame buffer settings.
	"""

	try:
		# Retrieve Stream Parameters device nodemap
		s_node_map = camera.GetTLStreamNodeMap()

		# Retrieve Buffer Handling Mode Information
		handling_mode = PySpin.CEnumerationPtr(s_node_map.GetNode("StreamBufferHandlingMode"))
		if not PySpin.IsAvailable(handling_mode) or not PySpin.IsWritable(handling_mode):
			print("Unable to set Buffer Handling mode (node retrieval). Aborting...")
			return cam_params

		handling_mode_entry = PySpin.CEnumEntryPtr(handling_mode.GetCurrentEntry())
		if not PySpin.IsAvailable(handling_mode_entry) or not PySpin.IsReadable(handling_mode_entry):
			print("Unable to set Buffer Handling mode (Entry retrieval). Aborting...")
			return cam_params

		# Set stream buffer Count Mode to manual
		stream_buffer_count_mode = PySpin.CEnumerationPtr(s_node_map.GetNode("StreamBufferCountMode"))
		if not PySpin.IsAvailable(stream_buffer_count_mode) or not PySpin.IsWritable(stream_buffer_count_mode):
			print("Unable to set Buffer Count Mode (node retrieval). Aborting...")
			return cam_params

		stream_buffer_count_mode_manual = PySpin.CEnumEntryPtr(stream_buffer_count_mode.GetEntryByName("Manual"))
		if not PySpin.IsAvailable(stream_buffer_count_mode_manual) or not PySpin.IsReadable(
				stream_buffer_count_mode_manual):
			print("Unable to set Buffer Count Mode entry (Entry retrieval). Aborting...")
			return cam_params

		stream_buffer_count_mode.SetIntValue(stream_buffer_count_mode_manual.GetValue())

		# Retrieve and modify Stream Buffer Count
		buffer_count = PySpin.CIntegerPtr(s_node_map.GetNode("StreamBufferCountManual"))
		if not PySpin.IsAvailable(buffer_count) or not PySpin.IsWritable(buffer_count):
			print("Unable to set Buffer Count (Integer node retrieval). Aborting...")
			return cam_params

		# Display Buffer Info
		buffer_count.SetValue(cam_params["bufferSize"])
		print("Buffer count now set to: %d" % buffer_count.GetValue())

		if cam_params["bufferMode"] == "OldestFirst":
			handling_mode_entry = handling_mode.GetEntryByName("OldestFirst")
		elif cam_params["bufferMode"] == "NewestFirst":
			handling_mode_entry = handling_mode.GetEntryByName("NewestFirst")
		elif cam_params["bufferMode"] == "NewestOnly":
			handling_mode_entry = handling_mode.GetEntryByName("NewestOnly")
		elif cam_params["bufferMode"] == "OldestFirstOverwrite":
			handling_mode_entry = handling_mode.GetEntryByName("OldestFirstOverwrite")
		else:
			print("BufferMode should be 'OldestFirst', 'NewestFirst', 'NewestOnly' or 'OldestFirstOverwrite'")
			return cam_params

		handling_mode.SetIntValue(handling_mode_entry.GetValue())
		print("BufferMode has been set to {}".format(handling_mode_entry.GetDisplayName()))

		cam_params["bufferSize"] = stream_buffer_count_mode_manual.GetValue()
		cam_params["bufferMode"] = handling_mode_entry.GetDisplayName()
	
	except Exception as e:
		logging.error('Caught exeption at cameras/flir.py ConfigureBuffer: {}'.format(e))

	return cam_params


def ConfigureChunkData(camera, cam_params):
	"""
	This function configures the camera to add chunk data to each image. It does
	this by enabling each type of chunk data before enabling chunk data mode.
	When chunk data is turned on, the data is made available in both the nodemap
	and each image.
	:param nodemap: Transport layer device nodemap.
	:type nodemap: INodeMap
	:return: True if successful, False otherwise
	:rtype: bool
	"""

	# ToDo: Only enable requested chunks (eg. Timestamp and FrameID) for faster execution and lower memory print
	
	try:
		if cam_params["cameraDebug"]:
			print("\n*** CONFIGURING CHUNK DATA ***\n")

		# Activate chunk mode
		#
		# *** NOTES ***
		# Once enabled, chunk data will be available at the end of the payload
		# of every image captured until it is disabled. Chunk data can also be
		# retrieved from the nodemap.

		nodemap = camera.GetNodeMap()
		chunk_mode_active = PySpin.CBooleanPtr(nodemap.GetNode("ChunkModeActive"))

		if PySpin.IsAvailable(chunk_mode_active) and PySpin.IsWritable(chunk_mode_active):
			chunk_mode_active.SetValue(True)

		# Enable all types of chunk data
		#
		# *** NOTES ***
		# Enabling chunk data requires working with nodes: "ChunkSelector"
		# is an enumeration selector node and "ChunkEnable" is a boolean. It
		# requires retrieving the selector node (which is of enumeration node
		# type), selecting the entry of the chunk data to be enabled, retrieving
		# the corresponding boolean, and setting it to be true.
		#
		# In this example, all chunk data is enabled, so these steps are
		# performed in a loop. Once this is complete, chunk mode still needs to
		# be activated.
		chunk_selector = PySpin.CEnumerationPtr(nodemap.GetNode("ChunkSelector"))

		if not PySpin.IsAvailable(chunk_selector) or not PySpin.IsReadable(chunk_selector):
			print("Unable to retrieve chunk selector. Aborting...")
			return cam_params

		# Retrieve entries
		#
		# *** NOTES ***
		# PySpin handles mass entry retrieval in a different way than the C++
		# API. Instead of taking in a NodeList_t reference, GetEntries() takes
		# no parameters and gives us a list of INodes. Since we want these INodes
		# to be of type CEnumEntryPtr, we can use a list comprehension to
		# transform all of our collected INodes into CEnumEntryPtrs at once.
		entries = [PySpin.CEnumEntryPtr(chunk_selector_entry) for chunk_selector_entry in chunk_selector.GetEntries()]

		# Retrieve corresponding boolean
		chunk_enable = PySpin.CBooleanPtr(nodemap.GetNode("ChunkEnable"))

		# Iterate through our list and select each entry node to enable
		for chunk_selector_entry in entries:
			if PySpin.IsAvailable(chunk_selector_entry) and PySpin.IsReadable(chunk_selector_entry):
				chunk_selector.SetIntValue(chunk_selector_entry.GetValue())
				chunk_name = chunk_selector_entry.GetSymbolic()
				chunk_str = "{}:".format(chunk_name)

				if PySpin.IsWritable(chunk_enable):
					if chunk_name=="FrameID" or chunk_name=="Timestamp":
						chunk_enable.SetValue(True)
					else:
						chunk_enable.SetValue(False)

				if cam_params["cameraDebug"]:
					if chunk_enable.GetValue() and PySpin.IsWritable(chunk_enable):
						print("{} enabled".format(chunk_str))
					elif not chunk_enable.GetValue() and PySpin.IsWritable(chunk_enable):
						print("{} disabled".format(chunk_str))
					else:
						print("{} not available".format(chunk_str))

	except Exception as e:
		logging.error("Caught error at cameras/flir.py at ConfigureChunkData: {}".format(e))

	return cam_params


def ConfigureExposure(camera, cam_params):
	"""
	This function configures a custom exposure time. Automatic exposure is turned off in order to allow for the
	customization, and then the custom setting is applied.
	 :param cam: Camera to configure exposure for.
	 :type cam: CameraPtr
	 :param exposure_time: exposure time in microseconds
	 :type exposure_time: int
	 :return: True if successful, False otherwise.
	 :rtype: bool
	"""
	
	try:
		if cam_params["cameraDebug"]:
			print("*** CONFIGURING EXPOSURE ***\n")
		# Turn off automatic exposure mode
		#
		# *** NOTES *** Automatic exposure prevents the manual configuration of exposure times and needs to be turned
		# off. Enumerations representing entry nodes have been added to QuickSpin. This allows for the much easier
		# setting of enumeration nodes to new values.
		#
		# The naming convention of QuickSpin enums is the name of the enumeration node followed by an underscore and
		# the symbolic of the entry node. Selecting "Off" on the "ExposureAuto" node is thus named "ExposureAuto_Off".

		if camera.ExposureAuto.GetAccessMode() != PySpin.RW:
			print("Unable to disable automatic exposure. Aborting...")
			return cam_params

		camera.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)

		# Set exposure time manually; exposure time recorded in microseconds
		#
		# *** NOTES *** Notice that the node is checked for availability and writability prior to the setting of the
		# node. In QuickSpin, availability and writability are ensured by checking the access mode.
		#
		# Further, it is ensured that the desired exposure time does not exceed the maximum. Exposure time is counted
		# in microseconds - this can be found out either by retrieving the unit with the GetUnit() method or by
		# checking SpinView.

		if camera.ExposureTime.GetAccessMode() != PySpin.RW:
			print("Unable to set exposure time. Aborting...")
			return cam_params

		# Ensure desired exposure time does not exceed the maximum
		exposure_time_to_set = cam_params["cameraExposureTimeInUs"]
		exposure_time_to_set = min(camera.ExposureTime.GetMax(), exposure_time_to_set)
		camera.ExposureTime.SetValue(exposure_time_to_set)
		print("Shutter time set to {} us...".format(exposure_time_to_set))
		cam_params["exposureTimeInUs"] = exposure_time_to_set

	except Exception as e:
		logging.error("Caught error at cameras/flir.py ConfigureExposure: {}".format(e))

	return cam_params


def ConfigureFrameHeight(camera, cam_params):
	"""
	This function configures the frame height to be captured in the region of interest. 
	Value is available to the user in the config.yaml:
	frameHeight: X
	Y offset is limited and centered automatically.
	"""
	try:
		# Set frame height
		nodemap = camera.GetNodeMap()

		height_to_set = cam_params["frameHeight"]
		if height_to_set % 16 != 0:
			while height_to_set % 16 != 0:
				height_to_set += 1
			cam_params["frameHeight"] = height_to_set

		# Get max offset values from the camera
		max_h = height_to_set
		try:
			max_h = PySpin.CIntegerPtr(nodemap.GetNode("Height")).GetMax()
		except Exception as e:
			logging.error("Caught exception at cameras/flir.py GetMax: {}".format(e))

		node_height = PySpin.CIntegerPtr(nodemap.GetNode("Height"))
		if PySpin.IsAvailable(node_height) and PySpin.IsWritable(node_height):
			height_to_set = cam_params["frameHeight"]
			node_height.SetValue(height_to_set)
			offset_y = int((max_h-height_to_set)/2)
			if offset_y % 4 != 0:
				while offset_y % 4 != 0:
					offset_y += 1
				print("offset_y is set to {}".format(offset_y))
			node_offset_y = PySpin.CIntegerPtr(nodemap.GetNode("OffsetY"))
			if PySpin.IsAvailable(node_offset_y) and PySpin.IsWritable(node_offset_y):
				node_offset_y.SetValue(offset_y)
				cam_params["offsetY"] = offset_y
			else:
				print("OffsetY cannot be set!")
		else:
			print("Height not available...")
		print("Height set to {}...".format(node_height.GetValue()))

	except Exception as e:
		logging.error("Caught exception at cameras/flir.py ConfigureFrameHeight: {}".format(e))

	return cam_params


def ConfigureFrameWidth(camera, cam_params):
	"""
	This function configures the frame width to be captured in the region of interest. 
	Value is available to the user in the config.yaml:
	frameWidth: X
	X offset is limited and centered automatically.
	"""
	try:

		nodemap = camera.GetNodeMap()
		# Set frame width
		width_to_set = cam_params["frameWidth"]
		if width_to_set % 16 != 0:
			while width_to_set % 16 != 0:
				width_to_set += 1
			cam_params["frameWidth"] = width_to_set

		# Get max offset values from the camera
		max_w = width_to_set
		try:
			max_w = PySpin.CIntegerPtr(nodemap.GetNode("Width")).GetMax()
		except Exception as e:
			logging.error("Caught exception at cameras/flir.py GetMax: {}".format(e))

		# *** NOTES ***
		# Other nodes, such as those corresponding to image width and height,
		# might have an increment other than 1. In these cases, it can be
		# important to check that the desired value is a multiple of the
		# increment. However, as these values are being set to the maximum,
		# there is no reason to check against the increment.
		node_width = PySpin.CIntegerPtr(nodemap.GetNode("Width"))
		if PySpin.IsAvailable(node_width) and PySpin.IsWritable(node_width):
			width_to_set = cam_params["frameWidth"]
			node_width.SetValue(width_to_set)
			print("Width set to {}...".format(node_width.GetValue()))
			offset_x = int((max_w-width_to_set)/2)
			if offset_x % 4 != 0:
				while offset_x % 4 != 0:
					offset_x += 1
				print("offset_x is set to {}".format(offset_x))
			node_offset_x = PySpin.CIntegerPtr(nodemap.GetNode("OffsetX"))
			if PySpin.IsAvailable(node_offset_x) and PySpin.IsWritable(node_offset_x):
				node_offset_x.SetValue(offset_x)
				cam_params["offsetX"] = offset_x
			else:
				print("OffsetX cannot be set!")
		else:
			print("Width not available...")

	except Exception as e:
		logging.error("Caught exception at cameras/flir.py ConfigureFrameWidth: {}".format(e))

	return cam_params


def ConfigureGain(camera, cam_params):
	"""
	This function configures the camera gain.
	:param cam: Camera to acquire images from.
	:type cam: CameraPtr
	:param gain: gain in dB
	:type gain: float
	:return: True if successful, False otherwise.
	:rtype: bool
	"""

	try:
		gain = cam_params["cameraGain"]
		if cam_params["cameraDebug"]:
			print("*** CONFIGURING GAIN ***\n")
	
		# Retrieve GenICam nodemap (nodemap)
		nodemap = camera.GetNodeMap()

		# Retrieve node
		node_gainauto_mode = PySpin.CEnumerationPtr(nodemap.GetNode("GainAuto"))
		if not PySpin.IsAvailable(node_gainauto_mode) or not PySpin.IsWritable(node_gainauto_mode):
			print("Unable to configure gain (enum retrieval). Aborting...")
			return cam_params

		# EnumEntry node (always associated with an Enumeration node)
		node_gainauto_mode_off = node_gainauto_mode.GetEntryByName("Off")
		if not PySpin.IsAvailable(node_gainauto_mode_off):
			print("Unable to configure gain (entry retrieval). Aborting...")
			return cam_params

		# Turn off Auto Gain
		node_gainauto_mode.SetIntValue(node_gainauto_mode_off.GetValue())

		# Retrieve gain node (float)
		node_gain = PySpin.CFloatPtr(nodemap.GetNode("Gain"))
		if not PySpin.IsAvailable(node_gain) or not PySpin.IsWritable(node_gain):
			print("Unable to configure gain (float retrieval). Aborting...")
			return cam_params

		max_gain = camera.Gain.GetMax()

		if gain > camera.Gain.GetMax():
			print("Max. gain is {}dB!".format(max_gain))
			gain = max_gain
		elif gain <= 0:
			gain = 0.0

		# Set gain
		node_gain.SetValue(float(gain))
		print("Gain set to {} dB.".format(gain))
		cam_params["gain"] = gain

	except Exception as e:
		logging.error("Caught error at cameras/flir.py ConfigureGain: {}".format(e))

	return cam_params


def ConfigureGamma(camera, cam_params):
	"""This function disables the gamma correction.
	:param cam: Camera to disable gamma correction.
	:type cam: CameraPtr
	"""

	try:
		if cam_params["disableGamma"]:
			if cam_params["cameraDebug"]:
				print("*** DISABLING GAMMA CORRECTION ***\n")

			# Retrieve GenICam nodemap (nodemap)
			nodemap = camera.GetNodeMap()

			# Retrieve node (boolean)
			node_gamma_enable_bool = PySpin.CBooleanPtr(nodemap.GetNode("GammaEnable"))

			if not PySpin.IsAvailable(node_gamma_enable_bool) or not PySpin.IsWritable(node_gamma_enable_bool):
				print("Unable to disable gamma (boolean retrieval). Aborting...")
				return cam_params

			# Set value to False (disable gamma correction)
			node_gamma_enable_bool.SetValue(False)
			print("Gamma correction disabled.")

	except Exception as e:
		logging.error("Caught error at cameras/flir.py at ConfigureGamma: {}".format(e))

	return cam_params


def ConfigurePixelFormat(camera, cam_params):
	"""
	This function configures the camera pixel format.
	:param cam: Camera to acquire images from.
	:type cam: CameraPtr
	:param pixelFormat: string 
	:type gain: str
	:return: True if successful, False otherwise.
	:rtype: bool
	"""
	
	try:
		pixelFormat = cam_params["pixelFormatInput"]

		if cam_params["cameraDebug"]:
			print("*** CONFIGURING PIXEL FORMAT ***\n")

		if pixelFormat == "bayer_rggb8" or pixelFormat == "bayer_bggr8":
			camera.PixelFormat.SetValue(PySpin.PixelFormat_BayerRG8)
			camera.IspEnable.SetValue(False)
		elif pixelFormat == "rgb24":
			camera.PixelFormat.SetValue(PySpin.PixelFormat_RGB8Packed)
		elif pixelFormat == "gray":
			camera.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
		else:
			eval("camera.PixelFormat.SetValue(PySpin.PixelFormat_{}".format(pixelFormat))

	except Exception as e:
		logging.error("Error setting pixel format to {}: {}".format(pixelFormat, e))

	return cam_params


def ConfigureTrigger(camera, cam_params):
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
	try:
		cam_params["configTrig"] = False
		if cam_params["cameraDebug"]:
				print("*** CONFIGURING TRIGGER ***")

		cameraTrigger = cam_params["cameraTrigger"]

		# Ensure trigger mode off
		# The trigger must be disabled in order to configure whether the source
		# is software or hardware.
		if camera.TriggerMode.GetAccessMode() != PySpin.RW:
			print("Unable to disable trigger mode (node retrieval). Aborting...")
			return cam_params
		camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)

		# Switch on the TriggerOverlap (important for high frame rates/exposures)
		camera.TriggerOverlap.SetValue(PySpin.TriggerOverlap_ReadOut)

		# Select trigger source
		# The trigger source must be set to hardware or software while trigger
		# mode is off.
		if camera.TriggerSource.GetAccessMode() != PySpin.RW:
			print("Unable to get trigger source (node retrieval). Aborting...")
			return cam_params

		# Configure trigger source
		if cameraTrigger == 'software' or cameraTrigger == 'Software' or cameraTrigger == 'SOFTWARE':
			camera.TriggerSource.SetValue(PySpin.TriggerSource_Software)
			print("Trigger source set to software...")
		elif str(cameraTrigger)=="None":
			camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)
			print("Trigger source set to None...")
			return cam_params
		else:
			eval("camera.TriggerSource.SetValue(PySpin.TriggerSource_{})".format(cameraTrigger))
			print("Trigger source set to {}...".format(cameraTrigger))

		# Turn trigger mode on
		# Once the appropriate trigger source has been set, turn trigger mode
		# on in order to retrieve images using the trigger.
		camera.TriggerMode.SetValue(PySpin.TriggerMode_On)
		cam_params["configTrig"] = True

	except Exception as e:
		logging.error("Caught error at cameras/flir.py ConfigureTrigger: {}".format(e))

	return cam_params


def PrintDeviceInfo(nodemap, cam_params):
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
	try:
		cam_num = cam_params["cameraSelection"]
		if cam_params["cameraDebug"]:
			print("Printing device information for camera %d... \n" % cam_num)

			node_device_information = PySpin.CCategoryPtr(nodemap.GetNode("DeviceInformation"))
			if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
				features = node_device_information.GetFeatures()
				for feature in features:
					node_feature = PySpin.CValuePtr(feature)
					try:
						print("%s: %s" % (node_feature.GetName(), node_feature.ToString() if PySpin.IsReadable(
							node_feature) else "Node not readable"))
					except:
						pass
			else:
				print("Device control information not available.")

	except Exception as e:
		logging.error("Caught error at cameras/flir.py PrintDeviceInfo: {}".format(e))


def GetConverter():
	# PySpin introduced "ImageProcessor" class 
	# instead of ImagePtr.Convert
	try:
		converter = PySpin.ImageProcessor()
		converter.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR)
	except:
		converter = None
	return converter


def ConvertBayerToRGB(converter, grabResult):
	img = converter.Convert(grabResult, PySpin.PixelFormat_RGB8)
	return img.GetNDArray()
