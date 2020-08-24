"""

"""
from imageio_ffmpeg import write_frames
import os
import time
import logging
import sys

def OpenWriter(
		cam_params,
		fname='0',
		ext='.mp4',
		codec='h264_nvenc',
		loglevel='quiet', # 'warning', 'quiet', 'info'
		):
	
	n_cam = cam_params["n_cam"]

	folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
	file_name = os.path.join(folder_name, fname + ext)

	if not os.path.isdir(folder_name):
		os.makedirs(folder_name)
		print('Made directory {}.'.format(folder_name))
	
	while(True):
		try:
			try:
				writer = write_frames(
							file_name,
							[cam_params["frameWidth"], cam_params["frameHeight"]], # size [W,H]
							fps=cam_params["frameRate"],
							quality=None,
							codec=codec,  # H.265 hardware accel'd (GPU) 'hevc_nvenc'; H.264 'h264_nvenc'
							pix_fmt_in=cam_params["pixelFormatInput"], # 'bayer_bggr8', 'gray', 'rgb24', 'bgr0', 'yuv420p'
							pix_fmt_out=cam_params["pixelFormatOutput"], # 'rgb0' (fastest), 'yuv420p'(slower), 'bgr0' (slower)
							bitrate=None,
							ffmpeg_log_level=loglevel, # 'warning', 'quiet', 'info'
							input_params=['-an'], # '-an' no audio
							output_params=[
								'-preset', 'fast', # set to 'fast', 'llhp', or 'llhq' for h264 or hevc
								'-qp', cam_params["quality"],
								'-r:v', str(cam_params["frameRate"]), # important to play nice with vsync '0'
								'-bf:v', '0',
								'-vsync', '0',
								'-2pass', '0',
								'-gpu', str(cam_params["gpu"]),
								],
							)
				writer.send(None) # Initialize the generator
				print('Opened: {} using GPU {}.'.format(file_name, cam_params["gpu"]))
				break
			except Exception as e:
				logging.error('Caught exception: {}'.format(e))
				time.sleep(0.1)

		except KeyboardInterrupt:
			break

	return writer

def WriteFrames(cam_params, writeQueue, stopQueue):

	n_cam = cam_params["n_cam"]

	# Start ffmpeg video writer 
	writer = OpenWriter(cam_params)
	message = ''

	# Continue writing...
	while(True):
		try:
			if writeQueue:
				message = writeQueue.popleft()
				if not isinstance(message, str):
					writer.send(message)
				elif message=='STOP':
					break
			else:
				time.sleep(0.0001)
		except KeyboardInterrupt:
			stopQueue.append('STOP GRABBING')

	# Closing up...
	print('Closing video writer for camera {}. Please wait...'.format(n_cam+1))
	time.sleep(1)
	writer.close()
