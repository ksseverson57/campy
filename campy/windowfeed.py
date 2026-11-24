"""
Frames for campy's one window (displayMode "one-window").

The window is a process of its own (campy/window.py) that draws every camera.
Each camera process sends it the frames it would have shown in its own window
(every frameRate/displayFrameRate-th frame, downsampled by the camera's
DisplayImage) through a multiprocessing queue of its own that holds at most
QUEUE_FRAMES frames. Sending never waits: when the window has not taken the
last frames yet (busy, closed by hand, or never opened), the frame is skipped
and the camera goes on grabbing. Only numpy and the standard library are used
here: the camera processes need nothing new.
"""

import queue

import numpy as np

PROCESS_NAME = "campy-window" # the window's process: campy.campy does not open the cameras in it
QUEUE_FRAMES = 2 # per camera, waiting for the window

queues = None # each camera's queue, in a camera process (SetQueues)


def SetQueues(cameraQueues):
	# Pool initializer: the camera processes get the queues as they start
	global queues
	queues = cameraQueues


class Feed:
	"""
	A camera's frames for the window. It stands in for the display queue
	of displayMode "per-camera": the camera's DisplayImage appends the
	downsampled frame to it, and unicam appends "STOP" when the camera stops.
	Next() gives the frame number, camera timestamp and write backlog of
	the frame that comes next, for the window's frame rate and health badge.
	"""

	def __init__(self, cam_params, cameraQueue):
		self.queue = cameraQueue
		# Never wait at exit for frames the window did not take (the window may be closed)
		self.queue.cancel_join_thread()
		self.info = {
			"camera": cam_params["n_cam"],
			"name": cam_params["cameraName"],
			"frameRate": float(cam_params["frameRate"]),
			}
		self.frame = {}
		self.sent = 0
		self.skipped = 0

	def Next(self, frameNumber, timeStamp, queued):
		self.frame = {"frameNumber": frameNumber, "timeStamp": timeStamp, "queued": queued}

	def append(self, img):
		if isinstance(img, str): # "STOP": the camera stopped grabbing
			self.Put({"ended": True}, timeout=1.0)
			return
		if self.queue.full():
			self.skipped += 1
			return
		# A copy of its own: the camera may reuse the frame's memory once it is released
		message = dict(self.frame, image=np.array(img))
		if self.Put(message):
			self.sent += 1
		else:
			self.skipped += 1

	def Put(self, message, timeout=None):
		message.update(self.info)
		try:
			if timeout is None:
				self.queue.put_nowait(message)
			else:
				self.queue.put(message, timeout=timeout)
			return True
		except (queue.Full, ValueError, OSError):
			return False


class WindowProcess:
	"""The window's process, as campy-acquire's main process starts and stops it."""

	def __init__(self, ctx, params):
		self.queues = [ctx.Queue(QUEUE_FRAMES) for n in range(params["numCams"])]
		self.stop = ctx.Event()
		self.process = ctx.Process(
			target=_Run,
			name=PROCESS_NAME,
			args=(self.queues, self.stop, WindowInfo(params)),
			daemon=True,
			)
		self.process.start()
		print("Showing all {} cameras in one window.".format(params["numCams"]))

	def Stop(self, timeout=5.0):
		# The recording ended: the window closes
		self.stop.set()
		self.process.join(timeout)
		if self.process.is_alive():
			self.process.terminate()
			self.process.join(1.0)
		if self.process.exitcode not in (0, None):
			print("The camera window stopped with exit code {}. The recording was not affected."\
				.format(self.process.exitcode))


def WindowInfo(params):
	# What the window knows before the first frames: the cameras' names, and the frame size they will likely have
	def First(value):
		return value[0] if isinstance(value, list) else value
	downsample = max(1, int(First(params["displayDownsample"])))
	names = params["cameraNames"]
	return {
		"names": [str(names[n]) if n < len(names) else "Camera{}".format(n) for n in range(params["numCams"])],
		"frameSize": (int(First(params["frameWidth"])) // downsample, int(First(params["frameHeight"])) // downsample),
		}


def _Run(cameraQueues, stop, info):
	# The window's process: Qt is loaded here only
	from campy import window
	window.Run(cameraQueues, stop, info)
