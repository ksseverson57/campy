"""consoleSummary: one line per camera when it is ready, and one when its video is closed."""

import os, sys
from collections import deque

from campy import startup, writer
from campy.cameras import unicam
from test_output_lines import Stdout, fake_camera_module, camera_params


def record(tmp_path, monkeypatch, writer_first=False, **more):
	# One camera's recording with a stand-in camera: what it prints, one entry per write
	monkeypatch.setattr(unicam, "ImportCam", lambda make: fake_camera_module())
	p = camera_params(tmp_path, **more)
	out = Stdout()
	monkeypatch.setattr(sys, "stdout", out)
	writeQueue, stopWriteQueue = deque(), deque([], 1)
	if writer_first:
		# As in a recording, the writer may open its video before the camera starts opening
		startup.Video("Opened: video using CPU to compress the stream.", p)
	unicam.GrabFrames(p, writeQueue, deque([], 2), deque([], 1), stopWriteQueue)
	writer.WriteFrames(p, writeQueue, deque([], 1), stopWriteQueue)
	monkeypatch.undo()
	assert [w for w in out.writes if not (w.endswith("\n") and w.count("\n") == 1)] == []
	return [w.rstrip("\n") for w in out.writes], p


def test_off_by_default_prints_what_campy_always_printed(tmp_path, monkeypatch):
	lines, p = record(tmp_path, monkeypatch)
	video = os.path.join(str(tmp_path), "Camera0", "v.mp4")
	assert [line.split(" at ")[0] for line in lines] == [
		"Opened Camera0: fake fake serial# 0",
		"Camera0 ready to trigger.",
		"Camera0 collected 10 frames",
		"Camera0 collected 20 frames",
		"Camera0 saved 20 frames",
		"Saved metadata for Camera0.",
		"Opened: {} using CPU to compress the stream.".format(video),
		"Closing video writer for Camera0. Please wait...",
		]


def test_on_one_line_when_ready_and_one_at_the_end(tmp_path, monkeypatch):
	lines, p = record(tmp_path, monkeypatch, writer_first=True, consoleSummary=True)
	video = os.path.join(str(tmp_path), "Camera0", "v.mp4")
	assert lines == [
		"Camera0 ready to trigger: fake fake serial 0, 16x16 at 100 fps, h264 on CPU -> {}".format(video),
		"Camera0 collected 10 frames at 100.0 fps for 0 sec.",
		"Camera0 collected 20 frames at 100.0 fps for 0 sec.",
		"Closing video writer for Camera0. Please wait...",
		"Camera0 saved 20 frames at 105 fps and its metadata: {} holds all of them.".format(video),
		]


def test_the_video_opened_after_the_ready_line_is_not_printed_twice(tmp_path, monkeypatch):
	# Here the writer opens its video after the camera is ready: the ready line named it already
	lines, p = record(tmp_path, monkeypatch, consoleSummary=True)
	assert not [line for line in lines if line.startswith("Opened")]


def test_settings_problems_and_a_camera_that_is_not_ready(monkeypatch):
	out = Stdout()
	monkeypatch.setattr(sys, "stdout", out)
	p = {"cameraName": "Camera1", "consoleSummary": True, "cameraMake": "flir", "cameraModel": "Blackfly S",
		"cameraSerialNo": "123", "frameWidth": 1280, "frameHeight": 1024, "offsetX": 0, "offsetY": 4,
		"frameRate": 80, "codec": "h265", "gpuID": 0, "gpuMake": "nvidia", "videoFolder": "data",
		"videoFilename": "0.mp4"}
	startup.Begin(p)
	startup.Step("Trigger source set to Line3...")
	startup.Setting("trigger", "trigger Line3")
	startup.Step("Gain set to 3 dB.")
	startup.Setting("gain", "gain 3 dB")
	startup.Warn("OffsetX cannot be set!") # at once, with the camera's name
	assert out.writes == ["Camera1: OffsetX cannot be set!\n"]
	assert startup.Summary(startup._camera, p) == "Camera1 ready to trigger: flir Blackfly S serial 123, " \
		"1280x1024 (offset 0,4) at 80 fps, trigger Line3, gain 3 dB, h265 on nvidia GPU 0 -> {}".format(
		os.path.join("data", "Camera1", "0.mp4"))
	startup.Failed("it did not start grabbing")
	startup.Failed("printed once")
	assert out.writes[1:] == ["Camera1 is not ready: it did not start grabbing. What it did as it opened:\n"
		"  Camera1: Trigger source set to Line3...\n  Camera1: Gain set to 3 dB.\n"]


def test_debug_mode_and_outside_a_recording_print_each_step_at_once(monkeypatch):
	out = Stdout()
	monkeypatch.setattr(sys, "stdout", out)
	startup.Step("Gain set to 3 dB.") # no camera opening: as before
	startup.Begin({"cameraName": "Camera0", "consoleSummary": True, "cameraDebug": True})
	startup.Step("Height set to 1024...")
	startup.Warn("OffsetY cannot be set!")
	startup.Ready({"cameraName": "Camera0"})
	assert out.writes == ["Gain set to 3 dB.\n", "Height set to 1024...\n", "OffsetY cannot be set!\n",
		"Camera0 ready to trigger.\n"]
