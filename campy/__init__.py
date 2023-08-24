def CampyParams():
	"""
	Default parameters for campy config.
	Omitted parameters will revert to these default values.
	""" 

	params = {}
	# Recording default parameters
	params["videoFolder"] = "./test"
	params["frameRate"] = 25
	params["recTimeInSec"] = 30
	params["numCams"] = 1
	params["cameraNames"] = ["Camera1"]

	# Camera default parameters
	params["cameraMake"] = "basler"
	params["cameraSettings"] = "./configs/calibration.pfs"
	params["frameWidth"] = 1152
	params["frameHeight"] = 1024
	params["zeroCopy"] = False

	# Flir camera default parameters
	params["bufferMode"] = "OldestFirst"
	params["cameraExposureTimeInUs"] = 750
	params["bufferSize"] = 500
	params["cameraGain"] = 1
	params["disableGamma"] = True
	params["cameraTrigger"] = "Line3"

	# Compression default parameters
	params["gpuID"] = "-1"
	params["pixelFormatInput"] = "rgb24"
	params["pixelFormatOutput"] = "rgb0"
	params["codec"] = "h264"
	params["quality"] = "10M"
	params["qualityMode"] = None

	# Display parameters
	params["chunkLengthInSec"] = 15
	params["displayFrameRate"] = 10
	params["displayDownsample"] = 4

	# Trigger parameters
	params["startArduino"] = 0
	params["serialPort"] = "COM3"

	# Other parameters
	params["ffmpegPath"] = []

	return params
