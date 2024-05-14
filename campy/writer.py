"""
Video writer class
"""
from imageio_ffmpeg import write_frames, get_ffmpeg_version
import os, sys, time, logging
from campy.utils.utils import QueueKeyboardInterrupt
from scipy import io as sio
import numpy as np
import math
import datetime

def OpenWriter(
	file_name, 
	cam_params, 
	queue,
):

	'''
	Initiate opening sequence for video writer
	'''
	try:
		writing = False
		folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
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
		g = str(int(cam_params["frameRate"]) * 5) # key-frame interval, ~every 5 seconds

		# Switch between constant quality (if quality is an integer, e.g., 25 or "25") 
		# and constant bitrate (if quality is a string with a character, e.g. "25M")
		if str(cam_params["qualityMode"])=="None" and quality.isdigit():
			quality_mode = "constqp"
		elif str(cam_params["qualityMode"])=="None" and not quality.isdigit():
			quality_mode = "cbr"
		else:
			quality_mode = cam_params["qualityMode"]

		# Load defaults
		gpu_params = []

		# CPU compression
		if cam_params["gpuID"] == -1:
			print("Opened Video [CPU]: {}".format(full_file_name))
			if str(preset)=="None":
				preset = "fast"
			gpu_params = [
						"-preset",preset,
						"-tune","fastdecode",
						"-crf",quality,
						"-bufsize","20M",
						"-maxrate","10M",
						"-bf:v","4",
						]

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
			print("Opened Video [GPU{}]: {}     ".format(cam_params["gpuID"], full_file_name))
			if cam_params["gpuMake"] == "nvidia":
				if str(preset)=="None":
					preset = "fast"
				gpu_params = [
							"-preset",preset,
							"-bf:v","0", # B-frame spacing "0"-"2" less intensive for encoding
							"-g",g, # I-frame spacing
							"-gpu",gpuID,
							# "-vf","atadenoise=0.02:0.04:0.02:0.04:0.02:0.04:5:all:p",
							]

				# Add quality mode (qp = constant quality; cbr = constant bit rate; vbr = variable bit rate)
				if quality_mode == "cbr":
					gpu_params.extend(["-b:v",quality, ]), # avg bitrate
				
				elif quality_mode == "vbr":
					if quality.isdigit():
						gpu_params.extend(["-q:v",quality, ]), # variable bitrate
					else:
						gpu_params.extend(["-q:v",quality, "-maxrate",quality]), # variable bitrate
				
				elif quality_mode == "constqp":
					gpu_params.extend(["-qp",quality, ]), # constant quality
				
				else:
					quality_mode == "cbr"
					quality = "10M"
					gpu_params.extend(["-b:v",quality, ]), # avg bitrate
					print("Could not set quality mode. Setting to default bit rate of 10M.")

				gpu_params.extend(["-rc",quality_mode, ])
				
				if cam_params["codec"] == "h264" or cam_params["codec"] == "H264":
					codec = "h264_nvenc"
				
				if cam_params["codec"] == "h265" or cam_params["codec"] == "H265" \
					or cam_params["codec"] == "hevc" or cam_params["codec"] == "HEVC":
					codec = "hevc_nvenc"
				
				elif cam_params["codec"] == "av1" or cam_params["codec"] == "AV1":
					codec = "av1_nvenc"

			# AMD GPU (AMF/VCE) encoder optimized parameters
			elif cam_params["gpuMake"] == "amd":
				print("Opened Video [GPU{}]: {} ".format(cam_params["gpuID"], full_file_name))
				# Preset not supported by AMF
				gpu_params = [
							"-usage", "lowlatency",
							"-rc", "cqp", # constant quantization parameter
							"-qp_i", quality,
							"-qp_p", quality,
							"-qp_b", quality,
							"-hwaccel_device", gpuID,
							]
				if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
					pix_fmt_out = "yuv420p"
				if cam_params["codec"] == "h264":
					codec = "h264_amf"
				elif cam_params["codec"] == "h265":
					codec = "hevc_amf"

			# Intel iGPU (Quick Sync) encoder optimized parameters
			elif cam_params["gpuMake"] == "intel":
				print("Opened Video [GPU{}]: {} ".format(full_file_name))
				if str(preset)=="None":
					preset = "faster"
				gpu_params = [
							"-bf:v", "0",
							"-preset", preset,
							"-q", str(int(quality)+1),
							]
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
				[cam_params["frameWidth"], cam_params["frameHeight"]],
				fps=cam_params["frameRate"],
				quality=None,
				codec=codec,
				pix_fmt_in=cam_params["pixelFormatInput"], 
				pix_fmt_out=pix_fmt_out,
				bitrate=None,
				ffmpeg_log_level=cam_params["ffmpegLogLevel"], 
				input_params=["-an"], 
				output_params=gpu_params,
				)
			writer.send(None)
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
	stopWriteQueue,
	stampQueue,
):
	ext = ".mp4"

	# Initialize counters
	writeCount = int(0)
	dropCount = int(0)
	curr_chunk = int(0)
	timestamps = list()
	frameNumbers = list()
	frameData = dict()

	# Initialize video chunks
	cam_params["chunkLengthInFrames"] = math.ceil(cam_params["chunkLengthInSec"] * cam_params["frameRate"])
	recTimeInFrames = math.ceil(cam_params["recTimeInSec"] * cam_params["frameRate"])
	num_chunks = math.ceil(cam_params["recTimeInSec"] / cam_params["chunkLengthInSec"])
	chunk_size = cam_params["chunkLengthInFrames"]

	# Set frame range of current chunk
	curr_chunk_range = np.asarray([0, chunk_size-1], dtype=np.int64)

	# Initialize video folder and filename data
	folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
	frameData["saveFolder"] = folder_name

	dt = f"{datetime.datetime.now(tz=None):%Y%m%d_%H%M%S}"
	filename = dt + "_" + str(curr_chunk_range[0]) + "-" + str(curr_chunk_range[1])
	currvideo_name = filename + ext
	frameData["filename"] = filename

	# Initialize first ffmpeg video writer
	writer, writing, readQueue = OpenWriter(currvideo_name, cam_params, stopGrabQueue)

	# Write chunks until interrupted and/or stop message received
	with QueueKeyboardInterrupt(readQueue):
		while(writing):
			if writeQueue:
				try:
					# Unpack dictionary containing the image and frame metadata
					im_dict = writeQueue.popleft()
					frameNumber = int(im_dict["frameNumber"])

					# Check if frame number is not in the current chunk range, 
					# otherwise open new video chunk
					if frameNumber not in range(curr_chunk_range[0], curr_chunk_range[1]+1):
						
						# Save timestamps and frameNumbers, saved as dictionary in queue
						frameData = dict()
						frameData["frameNumbers"] = frameNumbers
						frameData["timestamps"] = timestamps
						frameData["saveFolder"] = folder_name
						frameData["filename"] = filename
						stampQueue.append(frameData)

						curr_chunk = curr_chunk + 1
						if curr_chunk != num_chunks:

							# Reset timestamp and frameNumbers list
							timestamps = list()
							frameNumbers = list()

							# Set chunk frame start and end indices
							curr_chunk_range = curr_chunk_range + chunk_size
							if curr_chunk_range[-1] > recTimeInFrames:
								curr_chunk_range[-1] = recTimeInFrames - 1

							# Name the video for next chunk (date_time_framestart_frameend.ext)
							dt = f"{datetime.datetime.now(tz=None):%Y%m%d_%H%M%S}"
							filename = dt + "_" + str(curr_chunk_range[0]) + "-" + str(curr_chunk_range[1])
							currvideo_name = filename + ext

							# Close writer for previous video chunk
							writer.close()

							# Initialize next video chunk
							if curr_chunk in range(0, num_chunks):
								writer, _, _ = OpenWriter(
									currvideo_name, 
									cam_params, 
									stopGrabQueue
									)

					# Append timestamp
					frameNumbers.append(frameNumber)
					timestamps.append(im_dict["timestamp"])

					# Send image array to writer
					writer.send(im_dict["array"])
					writeCount += 1

				except Exception as e:
					dropCount += 1
					print('{} has dropped {} frames.'.format(
						cam_params["cameraName"],
						dropCount))
					print(e)

			else:
				# Once queue is depleted and grabbing stops, close the writer
				if stopWriteQueue:

					# Save timestamps and frameNumbers, saved as dictionary in queue
					frameData = dict()
					frameData["frameNumbers"] = frameNumbers
					frameData["timestamps"] = timestamps
					frameData["saveFolder"] = folder_name
					frameData["filename"] = filename
					stampQueue.append(frameData)

					# Close current writer and wait
					writer.close()

					# Write metadata files
					writing = CloseWriter(
						cam_params, 
						stopReadQueue, 
						writeCount, 
						dropCount,
						frameNumbers,
						timestamps)

				# Otherwise continue writing
				time.sleep(0.001)


def SaveTimestamps(stampQueue):
	
	saving = True

	while(saving):
		if stampQueue:
			try:
				frameData = stampQueue.popleft()

				# If stop message received, exit the loop
				if isinstance(stampQueue, str):
					saving = False
					break

				# Otherwise save timestamps and frameNumbers
				else:
					# Save frame data to formatted csv file
					framedata_filename = os.path.join(frameData["saveFolder"], frameData["filename"] + "_timestamps.csv")
					x = np.asarray([frameData["frameNumbers"],frameData["timestamps"]], dtype=np.double)
					x = x.T
					np.savetxt(os.path.normpath(framedata_filename), x, 
						delimiter=",", 
						header="frameNumber, timestamp (s)",
						fmt="%i,%1.4e")

					# Also save frame data to MATLAB file
					mat_filename = os.path.join(frameData["saveFolder"], frameData["filename"] + "_timestamps.mat")
					sio.savemat(os.path.normpath(mat_filename), frameData, do_compression=True)

			except KeyboardInterrupt:
				break

			except Exception as e:
				print(e)
				time.sleep(0.01)

		else:
			time.sleep(0.01)

	time.sleep(0.01)


def CloseWriter(
	cam_params, 
	stopQueue, 
	writeCount, 
	dropCount, 
	frameNumbers, 
	timestamps
):
	''' 
	Initiate closeout sequence for video writer
	'''

	# Send stop signal to frame grabber
	stopQueue.append("STOP")
	time.sleep(1)
	print('{} wrote {} and dropped {} frames.'.format(
		cam_params["cameraName"],
		writeCount,
		dropCount))

	time.sleep(1)

	return False