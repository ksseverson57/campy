"""Record synthetic frames through campy's writer with the CPU encoders, and read them back.

Needs the ffmpeg imageio-ffmpeg uses (conda-forge's in the README's environment),
built with libx264 and libx265. No camera or GPU.
"""

import os, re, subprocess
from collections import deque

import numpy as np
import pytest
import imageio_ffmpeg

from campy import writer

WIDTH, HEIGHT, FPS, SECONDS = 320, 240, 30, 2


def HasEncoder(name):
	out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-encoders"],
		capture_output=True, text=True).stdout
	return re.search(r"\s{}\s".format(name), out) is not None


def Frames(n):
	# A gray bar moving over a ramp, so every frame differs
	ramp = np.tile(np.linspace(0, 255, WIDTH, dtype=np.uint8), (HEIGHT, 1))
	for i in range(n):
		frame = ramp.copy()
		frame[:, (4 * i) % WIDTH:(4 * i) % WIDTH + 8] = 128
		yield np.repeat(frame[:, :, np.newaxis], 3, axis=2) # rgb24


def Record(tmp_path, **settings):
	cam_params = {
		"videoFolder": str(tmp_path),
		"cameraName": "Camera0",
		"videoFilename": "0.mp4",
		"cameraMake": "emu",
		"frameWidth": WIDTH,
		"frameHeight": HEIGHT,
		"frameRate": FPS,
		"pixelFormatInput": "rgb24",
		"pixelFormatOutput": "rgb0",
		"gpuID": -1,
		"gpuMake": "nvidia",
		"codec": "h264",
		"quality": 21,
		"preset": "None",
		"ffmpegLogLevel": "warning",
		}
	cam_params.update(settings)
	frames = deque(Frames(FPS * SECONDS))
	stopWriteQueue = deque([True], 1) # the grabber has already stopped: write the queue, then close
	writer.WriteFrames(cam_params, frames, deque([], 1), stopWriteQueue)
	return os.path.join(str(tmp_path), "Camera0", cam_params["videoFilename"])


def ReadBack(path):
	reader = imageio_ffmpeg.read_frames(path)
	meta = next(reader)
	count = sum(1 for _ in reader)
	return meta, count


def StreamInfo(path):
	# ffmpeg's description of the video stream, e.g. "Video: hevc (Main) (hvc1 / 0x31637668), ..."
	err = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", path],
		capture_output=True, text=True).stderr
	return [line for line in err.splitlines() if "Video:" in line][0]


@pytest.mark.parametrize("codec, encoder", [("h264", "libx264"), ("h265", "libx265")])
def test_cpu_recording_reads_back(tmp_path, codec, encoder):
	if not HasEncoder(encoder):
		pytest.skip("this ffmpeg has no {}".format(encoder))
	path = Record(tmp_path, codec=codec)
	meta, count = ReadBack(path)
	assert count == FPS * SECONDS
	assert tuple(meta["size"]) == (WIDTH, HEIGHT)
	assert meta["fps"] == FPS
	assert ("h264" if codec == "h264" else "hevc") in StreamInfo(path)


def test_mac_compatible_h265_recording(tmp_path):
	if not HasEncoder("libx265"):
		pytest.skip("this ffmpeg has no libx265")
	plain = Record(tmp_path / "plain", codec="h265")
	assert "hev1" in StreamInfo(plain)
	path = Record(tmp_path / "mac", codec="h265", macCompatibleH265=True)
	assert "hvc1" in StreamInfo(path)
	# libx265 writes its settings into the stream: closed GOPs only when asked
	assert b" open-gop" in open(plain, "rb").read()
	assert b"no-open-gop" in open(path, "rb").read()
	meta, count = ReadBack(path)
	assert count == FPS * SECONDS
