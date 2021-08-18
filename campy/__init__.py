def CampyParams():
	"""
	Default parameters for campy config.
	Omitted parameters will revert to these default values.
	""" 

	params = {}
	# Recording default parameters
	params["videoFolder"] = "./test"
	params["frameRate"] = 100
	params["recTimeInSec"] = 10
	params["numCams"] = 3
	params["cameraNames"] = ["Camera1","Camera2","Camera3"]

	# Camera default parameters
	params["cameraMake"] = "basler"
	params["cameraSettings"] = "./settings/acA1920-150uc_1152x1024p_100fps_trigger_RGB_p6.pfs"
	params["frameWidth"] = 1152
	params["frameHeight"] = 1024

	# Flir camera default parameters
	params["bufferMode"] = "OldestFirst"
	params["cameraExposureTimeInUs"] = 750
	params["bufferSize"] = 100
	params["cameraGain"] = 1
	params["disableGamma"] = True
	params["cameraTrigger"] = "Line3"

	# Compression default parameters
	params["gpuID"] = [0,0,0]
	params["pixelFormatInput"] = "rgb24" # "bayer_bggr8" "rgb24"
	params["pixelFormatOutput"] = "rgb0"
	params["codec"] = "h264"  
	params["quality"] = "21"

	# Display parameters
	params["chunkLengthInSec"] = 30
	params["displayFrameRate"] = 10
	params["displayDownsample"] = 2

	# Trigger parameters
	params["startArduino"] = 0
	params["serialPort"] = "COM3"

	# Other parameters
	params["ffmpegPath"] = [] #["/home/usr/Documents/ffmpeg/ffmpeg"]

	return params
