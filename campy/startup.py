"""
One line per camera when it is ready to trigger, and one when its video is
closed, instead of each setup step as it happens (consoleSummary: True).

All cameras open at the same time, one process each, and each prints every
setting as it sets it ("Height set to 1024...", "Gain set to 1 dB.", "Buffer
count now set to: 100", "Opened: ./test/Camera1/0.mp4 using CPU to compress
the stream."). With several cameras those lines are mixed together, and most
of them don't say which camera they are about. With consoleSummary on, each
camera process holds those steps (Step) and the values they set (Setting),
and prints them as one line once the camera is ready (Ready):

	Camera1 ready to trigger: flir Blackfly S BFS-U3-13Y3M serial 23501329, 1280x1024 at 80 fps,
	trigger Line3, exposure 750 us, gain 3 dB, gamma off, 100 buffers (Oldest First),
	h264 on CPU -> ./test/Camera1/0.mp4

(one line on the console). Problems still print at once, with the camera's
name in front (Warn). A camera that does not get ready (Failed) prints every
step it held, so what it did before it stopped is still there to read. At the
end, the camera's "saved N frames" and "Saved metadata" lines become one line
with what its video holds (Saved, MetadataSaved, Closed).

With consoleSummary off (the default), or cameraDebug on, every function here
prints what campy always printed, when it always printed it.
"""

import os, threading

from campy.utils.utils import Say

_lock = threading.Lock()
_camera = None # this process's camera, while it opens (one camera per process)


class _Camera:
	def __init__(self, name):
		self.name = name
		self.steps = [] # each held step's text, in order
		self.settings = {} # what the ready line says, by key, in the order first set
		self.ready = False # its ready line has been printed (or its steps, Failed)
		self.newFolder = False
		self.saved = None # (frames, fps) from SaveMetadata
		self.metadataSaved = False


def Wanted(cam_params):
	# Debug mode prints every step, as before
	return bool(cam_params.get("consoleSummary")) and not cam_params.get("cameraDebug")


def _Held(cam_params=None):
	"""
	This process's camera record, created on first use when consoleSummary is
	on: the writer may print before the camera starts opening.
	"""
	global _camera
	if _camera is None and cam_params is not None and Wanted(cam_params):
		_camera = _Camera(cam_params.get("cameraName", "camera"))
	return _camera


def Begin(cam_params):
	"""The camera starts opening: from here on its steps are held (when wanted)."""
	with _lock:
		_Held(cam_params)


def Step(text, cam_params=None):
	"""A step as the camera opens ("Gain set to 1 dB."): held until it is ready, else printed."""
	with _lock:
		camera = _Held(cam_params)
		if camera is not None and not camera.ready:
			camera.steps.append(str(text))
			return
	Say(text)


def Setting(key, text):
	"""What the ready line says for key ("gain": "gain 1 dB"); set again, replaced."""
	with _lock:
		if _camera is not None and not _camera.ready:
			_camera.settings[key] = str(text)


def Warn(text):
	"""A problem: printed at once, with the camera's name in front while its steps are held."""
	with _lock:
		name = _camera.name if _camera is not None and not _camera.ready else None
	text = str(text)
	if name and not text.startswith(name):
		text = "{}: {}".format(name, text)
	Say(text)


def Folder(text, cam_params):
	"""The writer's "Made directory <folder>.": the ready line says "(new folder)"."""
	with _lock:
		camera = _Held(cam_params)
		if camera is not None and not camera.ready:
			camera.steps.append(str(text))
			camera.newFolder = True
			return
	Say(text)


def Video(text, cam_params):
	"""
	The writer's "Opened: <video> using CPU to compress the stream.": the ready
	line names the video, so this is held, or left out once that line is printed.
	"""
	with _lock:
		camera = _Held(cam_params)
		if camera is not None:
			if not camera.ready:
				camera.steps.append(str(text))
			return
	Say(text)


def Ready(cam_params):
	"""The camera is ready to trigger: its one line (without consoleSummary, campy's usual line)."""
	with _lock:
		camera = _Held(cam_params)
		if camera is not None:
			camera.ready = True
			camera.steps = []
	if camera is None:
		Say("{} ready to trigger.".format(cam_params["cameraName"]))
		return
	Say(Summary(camera, cam_params))


def Failed(why=""):
	"""
	The camera will not get ready: every step it held, so what it did as it
	opened is still printed. Nothing when its ready line was printed.
	"""
	with _lock:
		camera = _camera
		if camera is None or camera.ready:
			return
		camera.ready = True
		steps, camera.steps = camera.steps, []
	if steps:
		Say("\n".join(["{} is not ready{}. What it did as it opened:".format(camera.name,
			": {}".format(why) if why else "")] + ["  {}: {}".format(camera.name, s.strip()) for s in steps if s.strip()]))


def Saved(cam_params, frames, fps):
	"""SaveMetadata's "<name> saved <frames> frames at <fps> fps.": with consoleSummary, part of the end line."""
	with _lock:
		camera = _Held(cam_params)
		if camera is not None:
			camera.saved = (frames, fps)
			return
	Say("{} saved {} frames at {} fps.".format(cam_params["cameraName"], frames, fps))


def MetadataSaved(cam_params):
	"""SaveMetadata's "Saved metadata for <name>.": with consoleSummary, part of the end line."""
	with _lock:
		camera = _Held(cam_params)
		if camera is not None:
			camera.metadataSaved = True
			return
	Say("Saved metadata for {}.".format(cam_params["cameraName"]))


def Closed(cam_params, frames_written, path):
	"""
	The writer has closed the video, which holds frames_written frames. With
	consoleSummary, the camera's end line: what it saved and what the video holds.
	"""
	with _lock:
		camera = _Held(cam_params)
	if camera is None:
		return
	Failed() # a camera that never got ready: what it did first
	name = camera.name
	if camera.saved is not None:
		frames, fps = camera.saved
		text = "{} saved {} frames at {} fps{}: {} holds {}.".format(name, frames, fps,
			" and its metadata" if camera.metadataSaved else "", path,
			"all of them" if frames_written == frames else "{} of them".format(frames_written))
	else:
		text = "{}: {} holds {} frames.".format(name, path, frames_written)
	if not camera.metadataSaved:
		text += " Its metadata was not saved (see the error above)."
	Say(text)


def Reset():
	"""Forget this process's camera (tests that record several cameras in one process)."""
	global _camera
	with _lock:
		_camera = None


def Summary(camera, cam_params):
	# "<name> ready to trigger: <make model serial>, <size> at <rate>, <settings...>, <video>"
	p = cam_params
	parts = []
	make = " ".join(str(x) for x in (p.get("cameraMake"), p.get("cameraModel")) if x not in (None, "", []))
	serial = p.get("cameraSerialNo")
	if serial not in (None, "", []):
		make = "{} serial {}".format(make, serial).strip()
	if make:
		parts.append(make)
	size = "{}x{}".format(p.get("frameWidth"), p.get("frameHeight"))
	if p.get("offsetX") or p.get("offsetY"):
		size = "{} (offset {},{})".format(size, p.get("offsetX") or 0, p.get("offsetY") or 0)
	try:
		size = "{} at {:g} fps".format(size, float(p["frameRate"]))
	except (KeyError, TypeError, ValueError):
		pass
	parts.append(size)
	parts.extend(camera.settings.values())
	parts.append(VideoText(p) + (" (new folder)" if camera.newFolder else ""))
	return "{} ready to trigger: {}".format(camera.name, ", ".join(parts))


def VideoText(cam_params):
	# "h264 on CPU -> <path>" or "h265 on nvidia GPU 0 -> <path>", as writer.OpenWriter opens it
	p = cam_params
	path = os.path.join(str(p.get("videoFolder")), str(p.get("cameraName")), str(p.get("videoFilename")))
	gpu = p.get("gpuID", -1)
	device = "CPU" if str(gpu) == "-1" else "{} GPU {}".format(p.get("gpuMake"), gpu)
	return "{} on {} -> {}".format(p.get("codec"), device, path)
