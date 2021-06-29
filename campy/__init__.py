def CampyParams():
	params = {}
	params["videoFolder"] = "./test"
	params["frameRate"] = 100
	params["recTimeInSec"] = 10

	# Camera parameters
	params["cameraMake"] = 'basler'
	params["cameraSettings"] = "./settings/acA1920-150uc_1152x1024p_100fps_trigger_RGB_p6.pfs"
	params["numCams"] = 6
	params["cameraNames"] = ['Camera1','Camera2','Camera3','Camera4','Camera5','Camera6']

	# Compression parameters
	params["gpuID"] = [0,0,0,2,2,2]
	params["pixelFormatInput"] = 'rgb24' # 'bayer_bggr8' 'rgb24'
	params["pixelFormatOutput"] = 'rgb0'
	params["quality"] = '21'

	# Display parameters
	params["chunkLengthInSec"] = 30
	params["displayFrameRate"] = 10
	params["displayDownsample"] = 2

	# Trigger parameters
	params["startArduino"] = 0
	params["serialPort"] = 'COM3'

	return params
