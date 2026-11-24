"""statusLine: one status line on the console while recording, instead of each camera's progress lines."""

import os, sys
from collections import deque

import pytest

from campy import statusline
from campy.cameras import unicam
from test_output_lines import Stdout, fake_camera_module, camera_params

CLEAR = statusline.ANSI_CLEAR


class Tty(Stdout):
	encoding = "utf-8"

	def isatty(self):
		return True


@pytest.fixture(autouse=True)
def no_status_line_env(monkeypatch):
	monkeypatch.delenv(statusline.ENV, raising=False)
	monkeypatch.setattr(statusline, "Width", lambda: 100)
	yield
	statusline.UseCounters(None)


def test_when_it_is_shown(monkeypatch):
	assert not statusline.Wanted("never", Tty())
	assert statusline.Wanted("auto", Tty())
	assert not statusline.Wanted("auto", Stdout()) # a file or a pipe keeps the "collected" lines
	assert statusline.Wanted("always", Stdout())
	assert statusline.Prepare({}, Tty(), Tty()) is None # default "never": the console as before
	assert not statusline.Shown()
	monkeypatch.setattr(statusline, "EnableVT", lambda stream=None: True) # the fake console has no Windows handle
	mode = statusline.Prepare({"statusLine": "auto"}, Tty(), Stdout())
	assert (mode.how, mode.stderr) == ("ansi", False)
	assert os.environ[statusline.ENV] == "ansi" and statusline.Shown()
	statusline.Prepare({"statusLine": "auto"}, Stdout(), Stdout())
	assert not statusline.Shown()


def test_a_camera_process_wipes_the_status_line_before_each_whole_line(monkeypatch):
	out = Stdout()
	stream = statusline.ChildStream(out, "ansi")
	stream.write("Camera0 ready")
	assert out.writes == [] # not half a line: the status line drawn after it would wipe it
	stream.write(" to trigger.\n")
	stream.write("two\nlines\n")
	assert out.writes == [CLEAR + "Camera0 ready to trigger.\n", CLEAR + "two\nlines\n"]
	monkeypatch.setenv(statusline.ENV, "pad,stderr")
	monkeypatch.setattr(sys, "stdout", Stdout())
	monkeypatch.setattr(sys, "stderr", Stdout())
	statusline.Child()
	assert isinstance(sys.stdout, statusline.ChildStream) and isinstance(sys.stderr, statusline.ChildStream)
	assert sys.stdout.how == "pad"


def test_a_message_lands_above_the_status_line(monkeypatch):
	out, err = Stdout(), Stdout()
	err.writes = out.writes # one console
	console = statusline.Console(out, err, "ansi")
	console.Draw("Recording 0:01")
	assert out.writes == [CLEAR + "Recording 0:01"]
	console.Write("stdout", "Closing systems...")
	console.Draw("Recording 0:02") # not drawn in the middle of a line
	console.Write("stdout", "\n")
	console.Write("stderr", "an error\n")
	console.Clear()
	assert out.writes[1:] == [CLEAR, "Closing systems...", "\n", CLEAR + "Recording 0:02",
		CLEAR, "an error\n", CLEAR + "Recording 0:02", CLEAR]


class Clocks:
	def __init__(self):
		self.now = 1000.0

	def clock(self):
		return self.now


def status(names=("Camera0", "Camera1")):
	counters = [0.0] * (statusline.FIELDS * len(names))
	clocks = Clocks()
	line = statusline.StatusLine(statusline.Mode("ansi", False), counters, names, clock=clocks.clock, wall=clocks.clock)
	line.started = clocks.now
	return line, counters, clocks


def set_camera(counters, c, frames, frame_time, state=statusline.GRABBING):
	counters[statusline.FIELDS * c:statusline.FIELDS * (c + 1)] = [frames, frame_time, state]


def test_what_it_says(monkeypatch):
	line, counters, clocks = status()
	clocks.now += 3
	assert line.Text() == "Waiting for the first frame 0:03 · Camera0 opening · Camera1 opening"
	for second in range(4):
		clocks.now += 1
		set_camera(counters, 0, 60 * (second + 1), clocks.now)
		set_camera(counters, 1, 60 * (second + 1), clocks.now)
		text = line.Text()
	assert text == "Recording 0:03 · Camera0 240 · Camera1 240 frames · 60.0 fps"
	clocks.now += 1
	set_camera(counters, 0, 300, clocks.now)
	set_camera(counters, 1, 290, clocks.now) # a slower camera: each camera's rate
	assert line.Text().endswith("Camera0 300 · Camera1 290 frames · fps 60.0/57.5")
	clocks.now += 65 # no frames: the trigger stopped
	assert line.Text() == "Recording 1:09 · Camera0 300 · Camera1 290 frames · no new frames for 1:05"
	set_camera(counters, 1, 290, clocks.now - 65, statusline.ENDED)
	assert "Camera1 ended at 290" in line.Text()


def test_it_fits_the_console(monkeypatch):
	names = ["Camera{}".format(n) for n in range(8)]
	line, counters, clocks = status(names)
	for c in range(8):
		set_camera(counters, c, 10800, clocks.now)
	monkeypatch.setattr(statusline, "Width", lambda: 80)
	text = line.Text()
	assert text.startswith("Recording 0:00 · frames 10,800 / 10,800 / ") and len(text) <= 80
	monkeypatch.setattr(statusline, "Width", lambda: 30)
	assert len(line.Text()) == 30 and line.Text().endswith("...")
	assert statusline.Clock(3 * 3600 + 62) == "3:01:02" and statusline.Clock(2 * 86400 + 5) == "2d 00:00:05"
	assert statusline.Separator("cp1252").sep == " · " and statusline.Separator("ascii").sep == " | "


def test_the_main_process_draws_it_and_gives_the_console_back(monkeypatch):
	out = Tty()
	monkeypatch.setattr(sys, "stdout", out)
	line, counters, clocks = status(["Camera0"])
	line.Start()
	print("All set") # print writes the text and its newline separately
	line.Stop()
	assert sys.stdout is out
	assert out.writes == [CLEAR + "Waiting for the first frame 0:00 · Camera0 opening", CLEAR,
		"All set", "\n", CLEAR + "Waiting for the first frame 0:00 · Camera0 opening", CLEAR]


def test_a_camera_counts_its_frames_and_skips_its_progress_lines_while_it_is_shown(tmp_path, monkeypatch):
	monkeypatch.setattr(unicam, "ImportCam", lambda make: fake_camera_module())
	counters = [0.0] * statusline.FIELDS
	statusline.UseCounters(counters)
	monkeypatch.setenv(statusline.ENV, "ansi")
	out = Stdout()
	monkeypatch.setattr(sys, "stdout", out)
	unicam.GrabFrames(camera_params(tmp_path), deque(), deque([], 2), deque([], 1), deque([], 1))
	monkeypatch.undo()
	assert counters[0] == 20 and counters[2] == statusline.ENDED and counters[1] > 0
	said = "".join(out.writes)
	assert "collected" not in said and "Camera0 ready to trigger." in said and "Camera0 saved 20 frames" in said
