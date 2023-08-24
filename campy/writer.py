"""
"""
import subprocess as sp
from imageio_ffmpeg import write_frames, get_ffmpeg_version
import os, sys, time, logging
from campy.utils.utils import QueueKeyboardInterrupt

def OpenWriter(cam_params, queue):
	try:
		writing = False
		folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
		file_name = cam_params["videoFilename"]
		full_file_name = os.path.normpath(os.path.join(folder_name, file_name))

		if not os.path.isdir(folder_name):
			os.makedirs(folder_name)

		# Flip blue and red for flir camera input
		if cam_params["pixelFormatInput"] == "bayer_bggr8" and cam_params["cameraMake"] == "flir":
			cam_params["pixelFormatInput"] == "bayer_rggb8"

		# Load encoding parameters from cam_params
		height = str(cam_params["frameHeight"])
		width = str(cam_params["frameWidth"])
		pix_fmt_out = str(cam_params["pixelFormatOutput"])
		quality = str(cam_params["quality"])
		codec = str(cam_params["codec"])
		preset = str(cam_params["preset"])
		frameRate = str(cam_params["frameRate"])
		gpuID = str(cam_params["gpuID"])
		g = str(int(cam_params["frameRate"]) * 5) # key-frame interval, every 5 seconds

		# Switch between constant quality (if quality is an integer, e.g., 25 or "25") 
		# and constant bitrate (if quality is a string with a character, e.g. "25M")
		if cam_params["qualityMode"] is None and quality.isdigit():
			quality_mode = "constqp"
		elif cam_params["qualityMode"] is None and not quality.isdigit():
			quality_mode = "cbr"
		else:
			quality_mode = cam_params["qualityMode"]

		# Load defaults
		gpu_params = None

		# CPU compression
		if cam_params["gpuID"] == -1:
			print("Opened: {} using CPU to compress the stream.".format(full_file_name))
			if preset == "None":
				preset = "fast"
			gpu_params = ["-r:v", frameRate,
						"-preset", preset,
						"-tune", "fastdecode",
						"-crf", quality,
						"-bufsize", "20M",
						"-maxrate", "10M",
						"-bf:v", "4",
						"-vsync", "0",]
			if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
				pix_fmt_out = "yuv420p"
			if cam_params["codec"] == "h264":
				codec = "libx264"
				gpu_params.extend(["-x264-params", "nal-hrd=cbr"])
			elif cam_params["codec"] == "h265":
				codec = "libx265"
			elif cam_params["codec"] == "av1":
				codec = "libaom-av1"

		# GPU compression
		else:
			# Nvidia GPU (NVENC) encoder optimized parameters
			print("Opened Video: {} using GPU {} to compress the stream.".format(full_file_name, cam_params["gpuID"]))
			if cam_params["gpuMake"] == "nvidia":
				if preset == None:
					preset = "fast"
				gpu_params = [
							"-preset",preset,
							"-bf:v","0", # B-frame spacing "0"-"2" less intensive for encoding
							"-g",g, # I-frame spacing
							"-gpu",gpuID,
							"-movflags","+faststart",
							] 

				if quality_mode == "cbr":
					gpu_params.extend(["-b:v",quality, ]), # variable/avg bitrate
				elif quality_mode == "constqp":
					gpu_params.extend(["-qp",quality, ]), # constant quality
				else:
					quality_mode == "cbr"
					quality = "10M"
					gpu_params.extend(["-b:v",quality, ]), # avg bitrate
					print("Could not set quality mode. \
						Setting to default bit rate of 10M.")
				gpu_params.extend(["-rc",quality_mode, ])
				
				if cam_params["codec"] == "h264" or cam_params["codec"] == "H264":
					codec = "h264_nvenc"
				if cam_params["codec"] == "h265" or cam_params["codec"] == "H265" \
					or cam_params["codec"] == "hevc" or cam_params["codec"] == "HEVC":
					codec = "hevc_nvenc"
				elif cam_params["codec"] == "av1" or cam_params["codec"] == "AV1":
					codec = "av1_nvenc"

				if get_ffmpeg_version() == "4.2.2":
					gpu_params.extend(["-vsync", "0"])
					gpu_params.extend(["-r:v", frameRate])
				else:
					gpu_params.extend(["-fps_mode", "passthrough"])

			# AMD GPU (AMF/VCE) encoder optimized parameters
			elif cam_params["gpuMake"] == "amd":
				# Preset not supported by AMF
				gpu_params = ["-r:v", frameRate,
							"-usage", "lowlatency",
							"-rc", "cqp", # constant quantization parameter
							"-qp_i", quality,
							"-qp_p", quality,
							"-qp_b", quality,
							"-hwaccel_device", gpuID,] # "-hwaccel", "auto",
				if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
					pix_fmt_out = "yuv420p"
				if cam_params["codec"] == "h264":
					codec = "h264_amf"
				elif cam_params["codec"] == "h265":
					codec = "hevc_amf"

			# Intel iGPU encoder (Quick Sync) optimized parameters				
			elif cam_params["gpuMake"] == "intel":
				if preset == "None":
					preset = "faster"
				gpu_params = ["-r:v", frameRate,
							"-bf:v", "0",
							"-preset", preset,
							"-q", str(int(quality)+1),]
				if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
					pix_fmt_out = "nv12"
				if cam_params["codec"] == "h264":
					codec = "h264_qsv"
				elif cam_params["codec"] == "h265":
					codec = "hevc_qsv"

	except Exception as e:
		logging.error("Caught exception at writer.py OpenWriter: {}".format(e))
		raise

	# Initialize writer object (imageio-ffmpeg)
	while(True):
		try:
			writer = write_frames(
				full_file_name,
				[cam_params["frameWidth"], cam_params["frameHeight"]], # size [W,H]
				fps=cam_params["frameRate"],
				quality=None,
				codec=codec,
				pix_fmt_in=cam_params["pixelFormatInput"], # "bayer_bggr8", "gray", "rgb24", "bgr0", "yuv420p"
				pix_fmt_out=pix_fmt_out,
				bitrate=None,
				ffmpeg_log_level=cam_params["ffmpegLogLevel"], # "warning", "quiet", "info"
				input_params=["-an"], # "-an" no audio
				output_params=gpu_params,
				)
			writer.send(None) # Initialize the generator
			writing = True
			break
			
		except Exception as e:
			logging.error("Caught exception at writer.py OpenWriter: {}".format(e))
			raise
			break

	# Initialize read queue object to enable signal interrupt user control
	readQueue = {}
	readQueue["queue"] = queue
	readQueue["message"] = "STOP"

	return writer, writing, readQueue

def WriteFrames(
	cam_params, 
	writeQueue, 
	stopGrabQueue, 
	stopReadQueue, 
	stopWriteQueue
):
	# Start ffmpeg video writer 
	writer, writing, readQueue = OpenWriter(cam_params, stopGrabQueue)
	writeCount = int(0)
	dropCount = int(0)

	with QueueKeyboardInterrupt(readQueue):
		# Write until interrupted and/or stop message received
		while(writing):
			if writeQueue:
				try:
					img = writeQueue.popleft()
					writer.send(img)
					writeCount += 1
				except Exception as e:
					dropCount += 1

			else:
				# Once queue is depleted and grabbing stops, stop writing
				if stopWriteQueue:
					stopReadQueue.append("STOP")
					time.sleep(1)
					print('{} wrote {} and dropped {} frames.'.format(
						cam_params["cameraName"],
						writeCount,
						dropCount))
					writing = False

				# Otherwise continue writing
				time.sleep(0.001)