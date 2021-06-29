"""
"""
from imageio_ffmpeg import write_frames
import os
import time
import logging
import sys

def OpenWriter(cam_params):
	writing = False
	folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
	file_name = cam_params["videoFilename"]
	full_file_name = os.path.join(folder_name, file_name)

	if not os.path.isdir(folder_name):
		os.makedirs(folder_name)
		print('Made directory {}.'.format(folder_name))
	
	# Load defaults
	pix_fmt_out = cam_params["pixelFormatOutput"]
	codec = cam_params["codec"]
	quality = str(cam_params["quality"])
	frameRate = str(cam_params["frameRate"])
	gpuID = str(cam_params["gpuID"])
	gpu_params = []
	

	# CPU compression
	if cam_params["gpuID"] == -1:
		print('Opened: {} using CPU to compress the stream.'.format(full_file_name))
		if pix_fmt_out == 'rgb0':
			pix_fmt_out = 'yuv420p'
		if cam_params["codec"] == 'h264':
			codec = 'libx264'
		elif cam_params["codec"] == 'h265':
			codec = 'libx265'
		gpu_params = ['-r:v', frameRate,
					'-preset', 'fast',
					'-tune', 'fastdecode',
					'-crf', quality,
					'-bufsize', '20M',
					'-maxrate', '10M',
					'-bf:v', '4',
					'-vsync', '0',]

	# GPU compression
	else:
		print('Opened: {} using GPU {} to compress the stream.'.format(full_file_name, cam_params["gpuID"]))
		if cam_params["gpuMake"] == 'nvidia':
			if cam_params["codec"] == 'h264':
				codec = 'h264_nvenc'
			elif cam_params["codec"] == 'h265':
				codec = 'hevc_nvenc'
			gpu_params = ['-r:v', frameRate, # important to play nice with vsync '0'
						'-preset', 'fast', # set to 'fast', 'llhp', or 'llhq' for h264 or hevc
						'-qp', quality,
						'-bf:v', '0',
						'-vsync', '0',
						'-2pass', '0',
						'-gpu', gpuID,]
		elif cam_params["gpuMake"] == 'amd':
			if pix_fmt_out == 'rgb0':
				pix_fmt_out = 'yuv420p'
			if cam_params["codec"] == 'h264':
				codec = 'h264_amf'
			elif cam_params["codec"] == 'h265':
				codec = 'hevc_amf'
			gpu_params = ['-r:v', frameRate,
						'-usage', 'lowlatency',
						'-rc', 'cqp', # constant quantization parameter
						'-qp_i', quality,
						'-qp_p', quality,
						'-qp_b', quality,
						'-bf:v', '0',
						'-hwaccel', 'auto',
						'-hwaccel_device', gpuID,]
		elif cam_params["gpuMake"] == 'intel':
			if pix_fmt_out == 'rgb0':
				pix_fmt_out = 'nv12'
			if cam_params["codec"] == 'h264':
				codec = 'h264_qsv'
			elif cam_params["codec"] == 'h265':
				codec = 'hevc_qsv'
			gpu_params = ['-r:v', frameRate,
						'-bf:v', '0',]

	# Initialize writer object (imageio-ffmpeg)
	while(True):
		try:
			writer = write_frames(
				full_file_name,
				[cam_params["frameWidth"], cam_params["frameHeight"]], # size [W,H]
				fps=cam_params["frameRate"],
				quality=None,
				codec=codec,
				pix_fmt_in=cam_params["pixelFormatInput"], # 'bayer_bggr8', 'gray', 'rgb24', 'bgr0', 'yuv420p'
				pix_fmt_out=pix_fmt_out,
				bitrate=None,
				ffmpeg_log_level=cam_params["ffmpegLogLevel"], # 'warning', 'quiet', 'info'
				input_params=['-an'], # '-an' no audio
				output_params=gpu_params,
				)
			writer.send(None) # Initialize the generator
			writing = True
			break

		except KeyboardInterrupt:
			break
			
		except Exception as e:
			logging.error('Caught exception: {}'.format(e))
			time.sleep(0.1)

	return writer, writing

def WriteFrames(cam_params, writeQueue, stopQueue):
	# Start ffmpeg video writer 
	writer, writing = OpenWriter(cam_params)
	message = ''

	# Write until interrupted or stop message received
	while(writing):
		try:
			if writeQueue:
				message = writeQueue.popleft()
				if isinstance(message, str) and message=='STOP':
					writing = False
				else:
					writer.send(message)
			else:
				time.sleep(0.001)
		except KeyboardInterrupt:
			stopQueue.append('STOP')

	# Close up...
	print('Closing video writer for {}. Please wait...'.format(cam_params["cameraName"]))
	writer.close()
	time.sleep(2)
