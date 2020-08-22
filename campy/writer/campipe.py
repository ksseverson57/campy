"""

"""
from imageio import get_writer
from imageio_ffmpeg import write_frames
import os
import time
import logging

def OpenWriter(
		c, # camera index
		videoFolder, # video folder
		frameRate,
		gpu=0, # idx of gpu
		quality=19, # int 0-55, 0 is lossless, 19-21 is "visually lossless"
		vf='scale=src_format=bayer_bggr8', # default 'scale=iw:ih' # debayer 'scale=src_format=bayer_bggr8'
		pixelFormatInput = 'rgb24', # 'rgb24' for RGB source, 'bayer_bggr8' for bayer source
		pixelFormatOutput = 'rgb0',
		fname='0',
		ext='.mp4',
		codec='h264_nvenc',
		loglevel='quiet', # 'warning', 'quiet', 'info'
		frameHeight=1024,
		frameWidth=1152,
		):

	folder_name = os.path.join(videoFolder, 'Camera' + str(c+1))
	file_name = os.path.join(folder_name, fname + ext)

	if not os.path.isdir(folder_name):
		os.makedirs(folder_name)
		print('Made directory {}.'.format(folder_name))
	
	while(True):
		try:
			try:
				writer = write_frames(
							file_name,
							[frameWidth, frameHeight], # size [W,H]
							fps=frameRate,
							quality=None,
							codec=codec,  # H.265 hardware accel'd (GPU) 'hevc_nvenc'; H.264 'h264_nvenc'
							pix_fmt_in=pixelFormatInput, # 'bayer_bggr8', 'gray', 'rgb24', 'bgr0', 'yuv420p'
							pix_fmt_out=pixelFormatOutput, # 'rgb0' (fastest), 'yuv420p'(slower), 'bgr0' (slower)
							bitrate=None,
							ffmpeg_log_level=loglevel, # 'warning', 'quiet', 'info'
							input_params=['-an'], # '-an' no audio
							output_params=[
								'-preset', 'fast', # set to 'fast', 'llhp', or 'llhq' for h264 or hevc
								'-qp', str(quality),
								'-r:v', str(frameRate), # important to play nice with vsync '0'
								'-bf:v', '0',
								'-vsync', '0',
								'-2pass', '0',
								'-gpu', str(gpu),
								],
							)

				writer.send(None) # Initialize the generator
				print('Opened:', file_name, 'using GPU', gpu)
				break
			except:
				time.sleep(0.1)

		except KeyboardInterrupt:
			break

	return writer

def WriteFrames(c, videoFolder, gpus, writeQueue, meta):

	frameRate = meta['FrameRate']
	recTimeInSec = meta['RecordingSetDuration']

	# Start ffmpeg video writer 
	writer = OpenWriter(
				c, 
				videoFolder, 
				frameRate, 
				gpu=gpus[c], 
				pixelFormatInput=meta['PixelFormatInput'],
				pixelFormatOutput=meta['PixelFormatOutput'],
				frameHeight=meta['FrameHeight'],
				frameWidth=meta['FrameWidth'])

	countOfImagesToGrab = recTimeInSec*frameRate
	message = ''

	while(True):
		if writeQueue:
			message = writeQueue.popleft()
			if not isinstance(message, str):
				# writer.append_data(message) # old imageio get_writer
				writer.send(message)
			elif message == 'STOP':
				try:
					print('Closing video writer for camera {}. Please wait...'.format(c+1))
					time.sleep(1)
					writer.close()
					break
				except KeyboardInterrupt:
					break
		else:
			time.sleep(0.0001)

