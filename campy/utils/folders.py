"""
Where a recording's files go.

By default (sessionFolder: False) each camera writes into
<videoFolder>/<cameraName>/, as campy always has.

With sessionFolder: True, each run of campy-acquire records into a new folder
inside videoFolder, named by the local date and time it started, laid out as
a session folder for multi-camera tools such as LUC3D and sleap-anipose:

	<videoFolder>/2026-11-24_14-05-11/
		Camera0/
			0.mp4
			frametimes.npy, frametimes.mat, metadata.csv
		Camera1/ ...

A calibration recording (a videoFilename with "calibration" in it, in any
case) puts each camera's video in <cameraName>/calibration_images/, where
those tools look for a camera's calibration video, and never take it for a
session video. The camera's other files stay in <cameraName>/.

The run's folder is made with os.mkdir, which fails if the folder is already
there, so no run records into another's: two runs started in the same second
get ..._14-05-11 and ..._14-05-11_2.
"""

import os, time

SESSION_FORMAT = "%Y-%m-%d_%H-%M-%S" # no colons: Windows paths cannot hold them
CALIBRATION_WORD = "calibration"
CALIBRATION_FOLDER = "calibration_images"


def SessionFolders(params):
	return params.get("sessionFolder", False) is True


def MakeSessionFolder(video_folder, now=None):
	"""
	Makes this run's folder inside video_folder, named by the local date and
	time, and returns its absolute path. A name already taken gets _2, _3, ...
	"""
	stamp = time.strftime(SESSION_FORMAT, time.localtime(now))
	os.makedirs(video_folder, exist_ok=True)
	count = 1
	while True:
		name = stamp if count == 1 else "{}_{}".format(stamp, count)
		path = os.path.join(video_folder, name)
		try:
			os.mkdir(path)
			return os.path.abspath(path)
		except FileExistsError:
			count += 1


def CheckCameraNames(params):
	"""
	Raises ValueError when two cameras would write into the same folder: their
	files would replace each other's. Compared ignoring case, since Windows and
	macOS folders do.
	"""
	seen = {}
	for name in params["cameraNames"]:
		key = str(name).casefold()
		if key in seen:
			raise ValueError("Cameras '{}' and '{}' would record into the same folder. "
				"Give each camera its own name (cameraNames).".format(seen[key], name))
		seen[key] = name


def RecordingFolder(cam_params):
	# This run's folder (sessionFolder), or videoFolder itself
	return cam_params.get("recordingFolder", cam_params["videoFolder"])


def CameraFolder(cam_params):
	# The camera's folder: its video, frame times and metadata
	return os.path.join(RecordingFolder(cam_params), cam_params["cameraName"])


def IsCalibrationVideo(cam_params):
	return CALIBRATION_WORD in os.path.basename(str(cam_params["videoFilename"])).lower()


def VideoFolder(cam_params):
	# Where the camera's video goes: its folder or, for a calibration video in
	# a session folder, calibration_images inside it
	folder = CameraFolder(cam_params)
	if SessionFolders(cam_params) and IsCalibrationVideo(cam_params):
		folder = os.path.join(folder, CALIBRATION_FOLDER)
	return folder
