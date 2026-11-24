"""denoise: ffmpeg's atadenoise before the encoder. No camera or GPU."""

import os
from collections import deque

import numpy as np
import pytest
import imageio_ffmpeg

from campy import writer
from campy.configurator import DefaultParams

from test_record import HasEncoder


def CamParams(**settings):
	cam_params = {
		"videoFilename": "0.mp4",
		"cameraName": "Camera0",
		"cameraMake": "emu",
		"frameWidth": 1280,
		"frameHeight": 1024,
		"frameRate": 30,
		"pixelFormatInput": "gray",
		"pixelFormatOutput": "rgb0",
		"gpuID": -1,
		"gpuMake": "nvidia",
		"codec": "h264",
		"quality": 21,
		"preset": "None",
		"ffmpegLogLevel": "warning",
		}
	cam_params.update(settings)
	return cam_params


def test_off_by_default():
	assert DefaultParams()["denoise"] == "None"
	assert writer.DenoiseArgs(CamParams()) == ([], [], 16)
	assert writer.DenoiseArgs(CamParams(denoise="None")) == ([], [], 16)


def test_atadenoise_runs_on_one_filter_thread():
	assert writer.DenoiseArgs(CamParams(denoise="atadenoise")) == \
		(["-filter_threads", "1"], ["-vf", "atadenoise=s=5"], 1)


def test_the_padding_imageio_ffmpeg_would_add_comes_after_the_filter():
	# 330x250 is padded to 336x256, as imageio-ffmpeg pads it without the filter
	assert writer.DenoiseArgs(CamParams(denoise="atadenoise", frameWidth=330, frameHeight=250)) == \
		(["-filter_threads", "1"], ["-vf", "atadenoise=s=5,scale=336:256"], 1)


def test_an_unknown_value_is_refused():
	with pytest.raises(ValueError, match='denoise is "None" or "atadenoise"'):
		writer.DenoiseArgs(CamParams(denoise="hqdn3d"))


@pytest.mark.parametrize("make, codec", [(None, "h264"), (None, "h265"), ("nvidia", "h264"), ("nvidia", "h265"),
	("intel", "h264"), ("intel", "h265"), ("amd", "h264"), ("amd", "h265")])
@pytest.mark.parametrize("denoise", ["None", "atadenoise"])
def test_the_command_campy_gives_ffmpeg(monkeypatch, tmp_path, make, codec, denoise):
	# What write_frames is called with, for every encoder: unchanged with the
	# setting off; with it on, one -vf (the filter), -filter_threads 1 before the
	# input, and no padding by imageio-ffmpeg
	calls = []

	def fake_write_frames(path, size, **kwargs):
		calls.append(kwargs)
		def gen():
			while True:
				yield
		return gen()

	monkeypatch.setattr(writer, "write_frames", fake_write_frames)
	settings = dict(codec=codec, videoFolder=str(tmp_path), denoise=denoise)
	if make is not None:
		settings.update(gpuID=0, gpuMake=make)
	cam_params = CamParams(**settings)
	writer.OpenWriter(cam_params, deque())
	[kwargs] = calls
	codec_name, pix_fmt_out, gpu_params = writer.EncoderArgs(CamParams(**settings))
	assert kwargs["codec"] == codec_name and kwargs["pix_fmt_out"] == pix_fmt_out
	if denoise == "None":
		assert kwargs["input_params"] == ["-an"]
		assert kwargs["output_params"] == gpu_params
		assert kwargs["macro_block_size"] == 16 # imageio-ffmpeg's default
	else:
		assert kwargs["input_params"] == ["-an", "-filter_threads", "1"]
		assert kwargs["output_params"] == gpu_params + ["-vf", "atadenoise=s=5"]
		assert kwargs["output_params"].count("-vf") == 1
		assert kwargs["macro_block_size"] == 1


WIDTH, HEIGHT, FRAMES = 160, 128, 30


def NoisyScene(seed=0):
	# A still gray background with sensor-like noise, and a bright square
	# moving 6 px a frame
	rng = np.random.default_rng(seed)
	for i in range(FRAMES):
		frame = np.clip(80 + rng.normal(0, 2.0, (HEIGHT, WIDTH)), 0, 255).astype(np.uint8)
		x = 10 + 6 * i
		frame[40:80, x:x + 30] = 220
		yield frame, x


def RecordGray(tmp_path, name, denoise):
	cam_params = CamParams(videoFolder=str(tmp_path), cameraName=name, frameWidth=WIDTH, frameHeight=HEIGHT,
		quality=0, denoise=denoise) # libx264 lossless (CRF 0)
	frames = deque(frame for frame, _ in NoisyScene())
	writer.WriteFrames(cam_params, frames, deque([], 1), deque([True], 1))
	path = os.path.join(str(tmp_path), name, "0.mp4")
	reader = imageio_ffmpeg.read_frames(path, pix_fmt="gray", bpp=1)
	meta = next(reader)
	return np.stack([np.frombuffer(f, np.uint8).reshape(HEIGHT, WIDTH) for f in reader]).astype(int)


def test_a_real_recording(tmp_path):
	if not HasEncoder("libx264"):
		pytest.skip("this ffmpeg has no libx264")
	plain = RecordGray(tmp_path, "plain", "None")
	smooth = RecordGray(tmp_path, "smooth", "atadenoise")
	assert plain.shape == smooth.shape == (FRAMES, HEIGHT, WIDTH)
	# No pixel moved by more than atadenoise's 4 gray levels (plus 1 for the
	# rounding of the range conversion to yuv420p and back)
	assert np.abs(smooth - plain).max() <= 5
	# The still background's noise went down, frame to frame (measured: the
	# frame-to-frame differences' spread 3.0 -> 2.1 gray levels)
	background = (slice(90, 120), slice(0, WIDTH))
	assert np.diff(smooth[:, background[0], background[1]], axis=0).std() < \
		0.8 * np.diff(plain[:, background[0], background[1]], axis=0).std()
	# The inside of the moving square is untouched, in every frame it is wholly in view
	checked = 0
	for i, (_, x) in enumerate(NoisyScene()):
		if 2 <= i < FRAMES - 2 and x + 30 <= WIDTH:
			checked += 1
			inside = (slice(45, 75), slice(x + 3, x + 27))
			assert np.abs(smooth[i][inside] - plain[i][inside]).max() <= 1
	assert checked >= 15
