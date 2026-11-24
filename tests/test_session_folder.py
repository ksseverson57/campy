"""
sessionFolder: each run records into a new <videoFolder>/<date_time>/ folder,
laid out as a session folder (one folder per camera, a calibration video in
<camera>/calibration_images/). Off by default: then every path is what campy
always wrote.
"""

import os
import re
import sys
import time

import pytest

from campy.utils import folders


def cam(**kw):
	p = {"videoFolder": os.path.join("data", "test"), "cameraName": "Camera0", "videoFilename": "0.mp4"}
	p.update(kw)
	return p


# ------------------------------------------------------------------ off (the default)

def test_off_writes_where_campy_always_did():
	for name in ("0.mp4", "calibration.mp4", "0-Calibration.mp4"):
		p = cam(videoFilename=name)
		old = os.path.join(p["videoFolder"], p["cameraName"])
		assert folders.CameraFolder(p) == old
		assert folders.VideoFolder(p) == old
		p["sessionFolder"] = False
		assert folders.VideoFolder(p) == old


def test_default_is_off():
	from campy import configurator
	assert configurator.DefaultParams()["sessionFolder"] is False


def parse(monkeypatch, tmp_path, config_text, *args):
	from argparse import ArgumentParser
	from campy import configurator
	path = tmp_path / "config.yaml"
	path.write_text(config_text)
	monkeypatch.setattr(sys, "argv", ["campy-acquire", str(path)] + list(args))
	clargs = configurator.ParseClargs(ArgumentParser())
	return configurator.CombineConfigAndClargs(clargs)


def test_an_existing_config_records_as_before(monkeypatch, tmp_path):
	params = parse(monkeypatch, tmp_path, 'videoFolder: "./test"\nnumCams: 2\n')
	assert params["sessionFolder"] is False
	assert not folders.SessionFolders(params)


@pytest.mark.parametrize("text,args,expected", [
	("sessionFolder: True\n", (), True),
	("sessionFolder: False\n", (), False),
	("", ("--sessionFolder", "True"), True),
	("sessionFolder: True\n", ("--sessionFolder", "False"), False), # the command line wins
])
def test_config_and_command_line(monkeypatch, tmp_path, text, args, expected):
	params = parse(monkeypatch, tmp_path, 'videoFolder: "./test"\n' + text, *args)
	assert params["sessionFolder"] is expected


def test_not_true_or_false_is_refused(monkeypatch, tmp_path):
	from campy import configurator
	path = tmp_path / "config.yaml"
	path.write_text('videoFolder: "./test"\nsessionFolder: "yes"\n')
	monkeypatch.setattr(sys, "argv", ["campy-acquire", str(path)])
	with pytest.raises(ValueError, match="sessionFolder must be True or False"):
		configurator.ConfigureParams()


# ------------------------------------------------------------------ on

def test_on_records_into_the_runs_folder():
	run = os.path.join("data", "test", "2026-11-24_14-05-11")
	p = cam(sessionFolder=True, recordingFolder=run)
	assert folders.CameraFolder(p) == os.path.join(run, "Camera0")
	assert folders.VideoFolder(p) == os.path.join(run, "Camera0")


@pytest.mark.parametrize("name", ["calibration.mp4", "0-calibration.mp4", "Calibration_0.mp4", "CALIBRATION.avi"])
def test_a_calibration_video_goes_into_calibration_images(name):
	run = os.path.join("data", "test", "2026-11-24_14-05-11")
	p = cam(sessionFolder=True, recordingFolder=run, videoFilename=name)
	# The video in calibration_images, the camera's other files beside it
	assert folders.VideoFolder(p) == os.path.join(run, "Camera0", "calibration_images")
	assert folders.CameraFolder(p) == os.path.join(run, "Camera0")


def test_other_videos_stay_in_the_camera_folder():
	p = cam(sessionFolder=True, recordingFolder="run", videoFilename="calib.mp4")
	assert folders.VideoFolder(p) == os.path.join("run", "Camera0")


def test_each_run_gets_a_new_folder(tmp_path):
	now = time.mktime((2026, 11, 24, 14, 5, 11, 0, 0, -1))
	base = tmp_path / "videos" # made if missing
	first = folders.MakeSessionFolder(str(base), now)
	(tmp_path / "videos" / "2026-11-24_14-05-11" / "Camera0").mkdir()
	second = folders.MakeSessionFolder(str(base), now)
	third = folders.MakeSessionFolder(str(base), now)
	assert [os.path.basename(f) for f in (first, second, third)] == \
		["2026-11-24_14-05-11", "2026-11-24_14-05-11_2", "2026-11-24_14-05-11_3"]
	assert all(os.path.isabs(f) and os.path.isdir(f) for f in (first, second, third))
	# The first run's folder is left as it was
	assert os.listdir(first) == ["Camera0"]
	assert os.listdir(second) == [] and os.listdir(third) == []


def test_the_folder_name_has_no_colons(tmp_path):
	name = os.path.basename(folders.MakeSessionFolder(str(tmp_path)))
	assert re.fullmatch(r"\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d", name)


def test_two_cameras_with_one_name_are_refused():
	folders.CheckCameraNames({"cameraNames": ["Camera0", "Camera1"]})
	for names in (["Camera0", "Camera0"], ["top", "side", "Top"]):
		with pytest.raises(ValueError, match="would record into the same folder"):
			folders.CheckCameraNames({"cameraNames": names})
