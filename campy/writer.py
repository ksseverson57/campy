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
	quality = str(cam_params["quality"])
	preset = str(cam_params["preset"])
	gpuID = str(cam_params["gpuID"])

	# Load defaults
	gpu_params = []

	# CPU compression
	if cam_params["gpuID"] == -1:
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

		# Intel iGPU encoder (Quick Sync) optimized parameters
		elif cam_params["gpuMake"] == "intel":
			if preset == "None":
				preset = "faster"
			gpu_params = [
					"-bf:v", "0",
					"-preset", preset,
					"-q", str(int(quality)+1),]
			# Quick Sync encodes 8-bit video from NV12 only: 4:2:0 like yuv420p,
			# with the two chroma planes interleaved. Given yuv420p, ffmpeg
			# switches to NV12 by itself and warns "Incompatible pixel format".
			if pix_fmt_out in ("rgb0", "bgr0", "yuv420p"):
				pix_fmt_out = "nv12"
			if cam_params["codec"] == "h264":
				codec = "h264_qsv"
			elif cam_params["codec"] == "h265":
				codec = "hevc_qsv"

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


# denoise: the ffmpeg filters each setting runs before the encoder
DENOISE_FILTERS = {
	"None": [],
	"atadenoise": ["atadenoise=s=5"],
	}


def DenoiseArgs(cam_params):
	"""
	Temporal denoising before encoding (denoise). "atadenoise" averages each
	pixel with the same pixel in the 2 frames before and the 2 after (s=5),
	but only while they differ from it by at most 4 gray levels (of 255,
	ffmpeg's default thresholds), so no pixel moves by more than 4, and a
	moving animal's edges, which change by tens of levels, are left alone.
	It runs on the CPU, first, on the frames as the camera sends them, before
	ffmpeg converts them to what the encoder takes (-pix_fmt).

	Returns (input_params, output_params, macro_block_size) to add to
	write_frames' arguments. "None" returns ([], [], 16): the command is
	exactly as without the setting.
	- -filter_threads 1: ffmpeg would otherwise start one filter thread per CPU
	  core for each camera (about 1.5 more cores for 8 cameras at 60 fps); on
	  one thread, about the CPU of no filter.
	- imageio-ffmpeg pads a frame whose size isn't a multiple of 16 with a -vf
	  of its own, which this -vf would replace (ffmpeg keeps only the last
	  -vf), so the padding is done here, after the filter, and imageio-ffmpeg
	  is told not to (macro_block_size 1).
	"""
	value = str(cam_params.get("denoise", "None"))
	if value not in DENOISE_FILTERS:
		raise ValueError('denoise is "None" or "atadenoise", not "{}".'.format(value))
	filters = list(DENOISE_FILTERS[value])
	if not filters:
		return [], [], 16
	width, height = int(cam_params["frameWidth"]), int(cam_params["frameHeight"])
	padded = (-(-width // 16) * 16, -(-height // 16) * 16)
	if padded != (width, height):
		filters.append("scale={}:{}".format(*padded))
	return ["-filter_threads", "1"], ["-vf", ",".join(filters)], 1

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
		denoise_input, denoise_output, macro_block_size = DenoiseArgs(cam_params)

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
				input_params=["-an"] + denoise_input, # "-an" no audio
				output_params=gpu_params + denoise_output,
				macro_block_size=macro_block_size,
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
    

