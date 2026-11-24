"""The camera side of the one window (displayMode "one-window"): sending frames never waits."""

import multiprocessing as mp
import os, subprocess, sys, textwrap, time

import numpy as np
import pytest

from campy import configurator, windowfeed
from campy.cameras import unicam


def CamParams(n_cam=0, **more):
	cam_params = {"n_cam": n_cam, "cameraName": "Camera{}".format(n_cam), "frameRate": 30,
		"cameraMake": "emu", "displayMode": "one-window"}
	cam_params.update(more)
	return cam_params


@pytest.fixture
def ctx():
	return mp.get_context("spawn")


def Drain(q, timeout=2.0):
	messages = []
	end = time.monotonic() + timeout
	while time.monotonic() < end:
		try:
			messages.append(q.get(timeout=0.1))
		except Exception:
			if messages:
				break
	return messages


def test_frames_arrive_with_their_number_time_and_camera(ctx):
	q = ctx.Queue(windowfeed.QUEUE_FRAMES)
	feed = windowfeed.Feed(CamParams(2), q)
	frame = np.full((24, 32, 3), 7, np.uint8)
	feed.Next(30, 1.5, 4)
	feed.append(frame)
	frame[:] = 0 # the camera reuses its frame's memory: the window still gets what was sent
	(message,) = Drain(q)
	assert message["camera"] == 2 and message["name"] == "Camera2" and message["frameRate"] == 30
	assert (message["frameNumber"], message["timeStamp"], message["queued"]) == (30, 1.5, 4)
	assert message["image"].shape == (24, 32, 3) and (message["image"] == 7).all()


def test_a_window_that_takes_nothing_never_holds_up_the_camera(ctx):
	# Nobody reads the queue (the window busy, closed, or never started): frames past the first few are skipped
	q = ctx.Queue(windowfeed.QUEUE_FRAMES)
	feed = windowfeed.Feed(CamParams(), q)
	frame = np.zeros((512, 576, 3), np.uint8) # a 1152 x 1024 frame at displayDownsample 2
	times = []
	for n in range(200):
		start = time.perf_counter()
		feed.Next(n, n / 30, 0)
		feed.append(frame[::1, ::1])
		times.append(time.perf_counter() - start)
	assert feed.sent == windowfeed.QUEUE_FRAMES
	assert feed.skipped == 200 - windowfeed.QUEUE_FRAMES
	assert max(times) < 0.05, max(times)
	assert sorted(times)[100] < 0.001 # a skipped frame costs next to nothing


def test_the_camera_stopping_is_sent_even_when_the_queue_was_full(ctx):
	q = ctx.Queue(windowfeed.QUEUE_FRAMES)
	feed = windowfeed.Feed(CamParams(1), q)
	for n in range(5):
		feed.Next(n, n / 30, 0)
		feed.append(np.zeros((4, 4), np.uint8))
	q.get(timeout=2) # the window takes one: room for the end
	feed.append("STOP")
	messages = Drain(q)
	assert messages[-1]["ended"] and messages[-1]["camera"] == 1


def test_window_info_takes_the_first_of_per_camera_lists():
	params = {"numCams": 3, "cameraNames": ["a", "b"], "frameWidth": [1280, 640, 640], "frameHeight": 1024,
		"displayDownsample": [2, 1, 1]}
	assert windowfeed.WindowInfo(params) == {"names": ["a", "b", "Camera2"], "frameSize": (640, 512)}


def test_display_mode_defaults_to_a_window_per_camera():
	assert configurator.DefaultParams()["displayMode"] == "per-camera"


def test_an_unknown_display_mode_falls_back_to_the_default(capsys):
	defaults = configurator.DefaultParams()
	params = dict(defaults, displayMode="grid")
	assert configurator.AutoParams(params, defaults)["displayMode"] == "per-camera"
	assert "displayMode set to invalid value" in capsys.readouterr().out
	params = dict(defaults, displayMode="one-window")
	assert configurator.AutoParams(params, defaults)["displayMode"] == "one-window"


def test_display_mode_from_the_command_line(monkeypatch, tmp_path):
	config = tmp_path / "config.yaml"
	config.write_text("numCams: 2\ncameraMake: emu\n")
	monkeypatch.setattr(sys, "argv", ["campy-acquire", str(config), "--displayMode", "one-window"])
	params = configurator.CombineConfigAndClargs(configurator.ParseClargs(configurator.ArgumentParser()))
	assert params["displayMode"] == "one-window"
	monkeypatch.setattr(sys, "argv", ["campy-acquire", str(config)])
	params = configurator.CombineConfigAndClargs(configurator.ParseClargs(configurator.ArgumentParser()))
	assert params["displayMode"] == "per-camera"


def test_basler_on_windows_uses_pylons_window_only_per_camera(monkeypatch):
	monkeypatch.setattr(sys, "platform", "win32")
	assert unicam.PylonWindow(CamParams(cameraMake="basler", displayMode="per-camera"))
	assert not unicam.PylonWindow(CamParams(cameraMake="basler", displayMode="one-window"))
	assert not unicam.PylonWindow(CamParams(cameraMake="flir", displayMode="per-camera"))
	monkeypatch.setattr(sys, "platform", "linux")
	assert not unicam.PylonWindow(CamParams(cameraMake="basler", displayMode="per-camera"))


def test_the_window_process_does_not_open_the_cameras(tmp_path):
	# Every process campy starts imports campy.campy, which opens the cameras from the config on the command
	# line. The window's process must not: here the config is missing, so opening the cameras fails
	script = tmp_path / "main.py"
	script.write_text(textwrap.dedent("""
		import sys
		sys.argv = ["campy-acquire", "no-such-config.yaml"]
		import multiprocessing as mp
		from campy import windowfeed
		if mp.current_process().name in (windowfeed.PROCESS_NAME, "other"):
			import campy.campy
		if __name__ == "__main__":
			ctx = mp.get_context("spawn")
			for name in (windowfeed.PROCESS_NAME, "other"):
				p = ctx.Process(target=windowfeed.SetQueues, args=(None,), name=name)
				p.start()
				p.join(60)
				print(name, p.exitcode)
		"""))
	env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.dirname(os.path.dirname(windowfeed.__file__))]
		+ ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])))
	out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120, env=env,
		cwd=str(tmp_path)).stdout
	assert "{} 0".format(windowfeed.PROCESS_NAME) in out, out
	assert "other 1" in out, out
