"""
"""
from imageio_ffmpeg import write_frames
import os, sys, time, logging
from campy.utils.utils import QueueKeyboardInterrupt

def EncoderArgs(cam_params):
	# ffmpeg settings for one camera's video: the encoder's name, the pixel
	# format it is given, and its options (passed after the input)
	pix_fmt_out = cam_params["pixelFormatOutput"]
	codec = str(cam_params["codec"])
	# quality: a CRF for libx264/libx265 and a constant quantizer for the GPU
	# encoders, 0-51 for H.264 and H.265. For AV1 it is AV1's quantizer
	# index, 0-255, passed to every GPU encoder as it is.
	quality = str(cam_params["quality"])
	preset = str(cam_params["preset"])
	gpuID = str(cam_params["gpuID"])

	# Load defaults
	gpu_params = []

	# CPU compression
	if cam_params["gpuID"] == -1:
		if cam_params["codec"] == "av1":
			# ffmpeg's own pick for "av1" (libaom-av1) refuses these options
			# ("Unable to parse "tune" option value "fastdecode"")
			raise ValueError('codec "av1" is encoded on a GPU only: set gpuID (0, 1, ...) '
				'and gpuMake ("nvidia", "intel" or "amd").')
		if preset == "None":
			preset = "fast"
		gpu_params = [
			"-preset", preset,
			"-tune", "fastdecode",
			"-crf", quality,
			"-bufsize", "20M",
			"-maxrate", "10M",
			"-bf:v", "4",
			]
		if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
			pix_fmt_out = "yuv420p"
		if cam_params["codec"] == "h264":
			codec = "libx264"
			gpu_params.append("-x264-params")
			gpu_params.append("nal-hrd=cbr")
		elif cam_params["codec"] == "h265":
			codec = "libx265"

	# GPU compression
	else:
		# Nvidia GPU (NVENC) encoder optimized parameters
		if cam_params["gpuMake"] == "nvidia":
			if preset == "None":
				preset = "fast"
			gpu_params = [
				"-preset", preset, # "fast" (= "p1" from ffmpeg 4.4), or "p1" (fastest) to "p7"; ffmpeg 9 dropped "llhp" and "llhq"
				"-qp", quality,
				"-bf:v", "0",
				"-gpu", gpuID,
				]
			if cam_params["codec"] == "h264":
				codec = "h264_nvenc"
			elif cam_params["codec"] == "h265":
				codec = "hevc_nvenc"
			elif cam_params["codec"] == "av1":
				codec = "av1_nvenc" # Ada (RTX 40-series, RTX Ada) and newer

		# AMD GPU (AMF/VCE) encoder optimized parameters
		elif cam_params["gpuMake"] == "amd":
			# Preset not supported by AMF
			gpu_params = [
				"-usage", "lowlatency",
				"-rc", "cqp", # constant quantization parameter
				"-qp_i", quality,
				"-qp_p", quality,
				"-qp_b", quality,
				"-bf:v", "0",]
			# No "-hwaccel_device": it is an input option, which ffmpeg refuses
			# among the output options ("cannot be applied to output url"), so
			# no AMF camera could start. AMF encodes on its default GPU.
			if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
				pix_fmt_out = "yuv420p"
			if cam_params["codec"] == "h264":
				codec = "h264_amf"
			elif cam_params["codec"] == "h265":
				codec = "hevc_amf"
			elif cam_params["codec"] == "av1":
				codec = "av1_amf" # RDNA 3 (Radeon RX 7000) and newer

		# Intel iGPU encoder (Quick Sync) optimized parameters
		elif cam_params["gpuMake"] == "intel":
			if preset == "None":
				preset = "faster"
			gpu_params = [
					"-bf:v", "0",
					"-preset", preset,
					# H.264 and H.265 get quality + 1, as campy always passed it;
					# AV1's quantizer index goes as it is
					"-q", quality if cam_params["codec"] == "av1" else str(int(quality)+1),]
			# Quick Sync encodes 8-bit video from NV12 only: 4:2:0 like yuv420p,
			# with the two chroma planes interleaved. Given yuv420p, ffmpeg
			# switches to NV12 by itself and warns "Incompatible pixel format".
			if pix_fmt_out in ("rgb0", "bgr0", "yuv420p"):
				pix_fmt_out = "nv12"
			if cam_params["codec"] == "h264":
				codec = "h264_qsv"
			elif cam_params["codec"] == "h265":
				codec = "hevc_qsv"
			elif cam_params["codec"] == "av1":
				codec = "av1_qsv" # Arc GPUs, and Core Ultra processors' integrated GPUs

		# Any other codec name (e.g. "hevc") reaches ffmpeg as it is, and ffmpeg
		# then picks its own encoder for it, which may well run on the CPU:
		# "av1" did, before campy mapped it to the GPU encoders
		if codec == str(cam_params["codec"]):
			logging.warning('codec "{}" is not one campy maps to a {} GPU encoder ("h264", "h265" or "av1"): '
				'ffmpeg picks its own encoder for it, which may run on the CPU.'.format(codec, cam_params["gpuMake"]))

	# macCompatibleH265: H.265 that Apple's decoder opens (MATLAB's VideoReader
	# on a Mac, QuickTime, Safari). It opens H.265 in an .mp4 or .mov only when
	# the file tags it "hvc1"; ffmpeg's own tag is "hev1", which it refuses
	# ("Cannot Decode"). hvc1 keeps the parameter sets in the file's header,
	# where ffmpeg puts them for every encoder. libx265 also writes closed GOPs:
	# its default open GOP makes each later keyframe a CRA frame whose leading
	# B-frames predict from the frames before it, which Apple's decoder fails
	# on even with hvc1, and a reader that seeks to one of those B-frames
	# gives the keyframe instead. The GPU encoders already write closed GOPs.
	if cam_params.get("macCompatibleH265", False) and cam_params["codec"] == "h265":
		if codec == "libx265":
			gpu_params += ["-x265-params", "open-gop=0"]
		extension = os.path.splitext(str(cam_params["videoFilename"]))[1].lower()
		if extension in (".mp4", ".mov"):
			gpu_params += ["-tag:v", "hvc1"]

	return codec, pix_fmt_out, gpu_params

def OpenWriter(cam_params, queue):
	try:
		writing = False
		folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
		file_name = cam_params["videoFilename"]
		full_file_name = os.path.join(folder_name, file_name)

		if not os.path.isdir(folder_name):
			os.makedirs(folder_name)
			print("Made directory {}.".format(folder_name))

		# Flip blue and red for flir camera input
		if cam_params["pixelFormatInput"] == "bayer_bggr8" and cam_params["cameraMake"] == "flir":
			cam_params["pixelFormatInput"] == "bayer_rggb8"

		# Load encoding parameters from cam_params
		if cam_params["gpuID"] == -1:
			print("Opened: {} using CPU to compress the stream.".format(full_file_name))
		else:
			print("Opened: {} using GPU {} to compress the stream.".format(full_file_name, cam_params["gpuID"]))
		codec, pix_fmt_out, gpu_params = EncoderArgs(cam_params)

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

	# Initialize read queue object to signal interrupt
	readQueue = {}
	readQueue["queue"] = queue
	readQueue["message"] = "STOP"

	return writer, writing, readQueue

def WriteFrames(cam_params, writeQueue, stopReadQueue, stopWriteQueue):
	# Start ffmpeg video writer 
	writer, writing, readQueue = OpenWriter(cam_params, stopReadQueue)

	with QueueKeyboardInterrupt(readQueue):
		# Write until interrupted and/or stop message received
		while(writing):
			if writeQueue:
				writer.send(writeQueue.popleft())
			else:
				# Once queue is depleted and grabber stops, then stop writing
				if stopWriteQueue:
					writing = False
				# Otherwise continue writing
				time.sleep(0.01)

	# Close up...
	print("Closing video writer for {}. Please wait...".format(cam_params["cameraName"]))
	time.sleep(1)
	writer.close()
    

