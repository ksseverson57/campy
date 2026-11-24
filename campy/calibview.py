"""
Calibration view, over the one window (displayMode "one-window", campy/window.py).

Press c in the window, or set calibrationMode: True, and each camera's tile
shows, over its frames:
	- the ChArUco board's corners found in it (yellow dots), or, while a
	  board set to "auto" is still being identified, its markers (cyan);
	- where corners have been seen so far (green cells), so you can move the
	  board until every part of each camera's view has been covered;
	- the number of views where the camera saw the board well (MIN_CORNERS
	  corners or more), and, for each other camera, the frames both saw it
	  in (what the cameras' positions are calibrated from).

It runs in the window's process only, on the frames the window is sent
(every frameRate/displayFrameRate-th frame, downsampled by
displayDownsample), never in a camera process. A thread of its own detects
on one frame per camera at most every DETECT_EVERY_S seconds, the same frame
number for every camera (so that cameras on one trigger can be paired), and
rests at least as long as it worked, so it never takes more than half a
core. It skips the frames that come while it is busy: a slow detector shows
fewer updates and never holds up drawing or the recording.

Needs OpenCV 4.7 or newer (cv2.aruco.CharucoDetector), imported only when
the view is turned on: without it the tiles say what to install.
"""

import threading, time

import numpy as np

from campy.utils import boards

DETECT_EVERY_S = 0.2 # one frame set (a frame of each camera) at most this often
MIN_CORNERS = 6 # a view with this many corners counts
COVER = (16, 12) # the coverage map's cells, across and down
PENDING = 6 # frames kept per camera, waiting for detection
SHOW_S = 1.0 # a detection is drawn for this long
IDENTIFY_EVERY = 4 # "auto": identify the board after this many more images with markers
IDENTIFY_KEEP = 40 # ...from the newest this many
GOOD_VIEWS, GOOD_PAIRS = 30, 15 # shown in green from here (a rough guide, not a rule)


def LoadCv2():
	"""(cv2, None), or (None, what to install)."""
	try:
		import cv2
	except ImportError:
		return None, "needs OpenCV 4.7 or newer: pip install opencv-python"
	if not hasattr(cv2, "aruco") or not hasattr(cv2.aruco, "CharucoDetector"):
		return None, "needs OpenCV 4.7 or newer (this is {}): pip install -U opencv-python".format(cv2.__version__)
	return cv2, None


class Detector:
	"""The board's corners in a frame, with OpenCV (no Qt). board: boards.Board()."""

	def __init__(self, board, cv2, squareMm=None):
		self.cv2 = cv2
		self.board = board
		self.squareMm = board.get("square_length", squareMm) if board.get("preset") == boards.AUTO else None
		self.charuco = None
		self.status, self.candidates, self.reason = "match", [], ""
		self.observations = []
		self.sinceIdentify = 0
		if board.get("preset") == boards.AUTO:
			self.status, self.reason = "undecided", "looking for calib.io markers (DICT_5X5)"
			d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
			self.markers = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
		else:
			self.Use(board)

	def Use(self, board):
		cv2 = self.cv2
		d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, boards.DictName(board)))
		charuco = cv2.aruco.CharucoBoard((board["board_x"], board["board_y"]), float(board["square_length"]),
			float(board["marker_length"]), d)
		self.charuco = cv2.aruco.CharucoDetector(charuco)

	def Found(self):
		"""The board found ("auto": once identified, the size picked or not), or None."""
		if self.status in ("match", "size-ambiguous") and self.candidates:
			return boards.PresetBoard(self.candidates[0])
		return self.board if self.board.get("preset") != boards.AUTO else None

	def Detect(self, image):
		"""(corners: n x 2, markers: [4 x 2]) in image's pixels."""
		cv2 = self.cv2
		gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
		if self.charuco is not None:
			corners, ids, markers, markerIds = self.charuco.detectBoard(gray)
			corners = np.zeros((0, 2)) if corners is None else corners.reshape(-1, 2)
			return corners, [m.reshape(4, 2) for m in (markers or ())]
		markers, ids, _ = self.markers.detectMarkers(gray)
		markers = [m.reshape(4, 2) for m in (markers or ())]
		if ids is not None and len(ids) >= boards.IDENTIFY["minMarkers"]:
			self.observations = self.observations[-(IDENTIFY_KEEP - 1):] + [(ids.ravel().tolist(), markers)]
			self.sinceIdentify += 1
			if self.sinceIdentify >= IDENTIFY_EVERY:
				self.sinceIdentify = 0
				self.status, self.candidates, self.reason = boards.Identify(self.observations, self.squareMm)
				if self.status in ("match", "size-ambiguous"):
					# Every size of one grid has its markers in the same places: any finds the corners
					self.Use(boards.PresetBoard(self.candidates[0]))
					self.observations = []
		return np.zeros((0, 2)), markers


class Coverage:
	"""Where one camera has seen the board's corners, and in how many views."""

	def __init__(self):
		self.cells = np.zeros((COVER[1], COVER[0]), np.int64)
		self.views = 0

	def Add(self, corners, size):
		if len(corners) < MIN_CORNERS:
			return False
		w, h = size
		cx = np.clip((corners[:, 0] / w * COVER[0]).astype(int), 0, COVER[0] - 1)
		cy = np.clip((corners[:, 1] / h * COVER[1]).astype(int), 0, COVER[1] - 1)
		np.add.at(self.cells, (cy, cx), 1)
		self.views += 1
		return True

	def Covered(self):
		return float((self.cells > 0).mean())


class CalibrationView:
	"""
	The calibration view's state and detection thread (no Qt but in
	Overlay). names: the cameras'. board: boards.Board(), or None for "auto".
	"""

	def __init__(self, names, board=None, squareMm=None, loader=LoadCv2, every=DETECT_EVERY_S, threaded=True):
		self.names = list(names)
		n = len(self.names)
		self.board = board or boards.Board(boards.AUTO, squareMm)
		self.squareMm = squareMm
		self.loader = loader
		self.every = every
		self.threaded = threaded # False: no thread; Step() detects (the tests)
		self.on = False
		self.problem = None
		self.detector = None
		self.lock = threading.Lock()
		self.pending = [dict() for _ in range(n)] # frame number -> image
		self.latest = [None] * n # (time, frame number, corners, markers)
		self.coverage = [Coverage() for _ in range(n)]
		self.pairs = np.zeros((n, n), np.int64)
		self.sets = 0 # frame sets detected
		self.busy = 0.0 # seconds spent detecting
		self.cpu = 0.0 # of them, CPU seconds of the detection thread
		self.running = 0.0 # seconds the view was on
		self.onSince = None
		self.thread = None
		self.quit = threading.Event()

	# ------------------------------------------------------------ on and off

	def Toggle(self):
		self.Stop() if self.on else self.Start()

	def Start(self):
		self.on, self.onSince = True, time.monotonic()
		if self.detector is None and self.problem is None:
			cv2, self.problem = self.loader()
			if cv2 is not None:
				try:
					self.detector = Detector(self.board, cv2, self.squareMm)
				except Exception as e:
					self.problem = "could not set up the board: {}".format(e)
		if self.detector is not None and self.thread is None and self.threaded:
			self.thread = threading.Thread(target=self.Loop, name="campy calibration view", daemon=True)
			self.thread.start()

	def Stop(self):
		if self.on and self.onSince is not None:
			self.running += time.monotonic() - self.onSince
		self.on, self.onSince = False, None
		with self.lock:
			for p in self.pending:
				p.clear()

	def Close(self):
		self.Stop()
		self.quit.set()
		if self.thread is not None:
			self.thread.join(5.0)

	# ------------------------------------------------------------ frames in, detection

	def Take(self, camera, message):
		# Window.watchers: every frame message the window takes
		if not self.on or self.detector is None or "image" not in message or message.get("frameNumber") is None:
			return
		with self.lock:
			pending = self.pending[camera]
			pending[message["frameNumber"]] = message["image"]
			while len(pending) > PENDING:
				del pending[min(pending)]

	def Next(self):
		"""
		The next frame set: (frame number, {camera: image}), the frame number
		most cameras have (the newest of those). A frame number not every
		camera has sent yet waits until a newer one comes, so that the
		cameras still sending it are not left out.
		"""
		with self.lock:
			counts = {}
			for pending in self.pending:
				for number in pending:
					counts[number] = counts.get(number, 0) + 1
			newest = max(counts) if counts else None
			counts = {k: n for k, n in counts.items() if n == len(self.pending) or k < newest}
			if not counts:
				return None, {}
			number = max(counts, key=lambda k: (counts[k], k))
			images = {c: pending[number] for c, pending in enumerate(self.pending) if number in pending}
			for pending in self.pending:
				for k in [k for k in pending if k <= number]:
					del pending[k]
		return number, images

	def Step(self):
		"""Detects on one frame set; returns how many frames."""
		number, images = self.Next()
		if not images:
			return 0
		t0, c0 = time.perf_counter(), time.thread_time()
		seen = []
		for camera, image in images.items():
			image = np.asarray(image)
			corners, markers = self.detector.Detect(image)
			size = (image.shape[1], image.shape[0])
			with self.lock:
				self.latest[camera] = (time.monotonic(), number, corners, markers)
				if self.coverage[camera].Add(corners, size):
					seen.append(camera)
		with self.lock:
			for i in seen:
				for j in seen:
					if i != j:
						self.pairs[i, j] += 1
			self.sets += 1
			self.busy += time.perf_counter() - t0
			self.cpu += time.thread_time() - c0
		return len(images)

	def Loop(self):
		while not self.quit.is_set():
			t0 = time.monotonic()
			if self.on:
				try:
					self.Step()
				except Exception as e:
					self.problem = "detection failed: {}".format(e)
					self.on = False
			worked = time.monotonic() - t0
			# Every DETECT_EVERY_S, and resting at least as long as it worked: at most half a core
			self.quit.wait(max(0.01, self.every - worked, worked))

	# ------------------------------------------------------------ what it found

	def Lines(self, camera):
		"""What camera's tile says: [(text, colour name)]."""
		if self.problem:
			return [("CALIBRATION " + self.problem, "bad")]
		cov = self.coverage[camera]
		lines = [("CALIBRATION  {:,} views  {:.0f}% of the frame covered".format(cov.views, 100 * cov.Covered()),
			"good" if cov.views >= GOOD_VIEWS else "text")]
		others = [(self.names[j], int(self.pairs[camera, j])) for j in range(len(self.names)) if j != camera]
		if others:
			lines.append(("with " + "  ".join("{} {:,}".format(n, k) for n, k in others),
				"bad" if min(k for _, k in others) == 0 else "good" if min(k for _, k in others) >= GOOD_PAIRS else "text"))
		d = self.detector
		if d is not None and self.board.get("preset") == boards.AUTO:
			if d.status == "match":
				lines.append(("board: " + boards.Label(d.candidates[0]), "text"))
			elif d.status == "size-ambiguous":
				lines.append(("board: " + " or ".join(p["sku"] for p in d.candidates) + " (set calibrationSquareMm)", "text"))
			else:
				lines.append(("board: " + d.reason, "bad" if d.status == "no-match" else "text"))
		return lines

	def CpuShare(self):
		"""The share of one core the detection used while the view was on."""
		running = self.running + (time.monotonic() - self.onSince if self.onSince is not None else 0.0)
		return self.cpu / running if running > 0 else 0.0

	def Summary(self):
		if self.problem:
			return "Calibration view: " + self.problem
		if not self.sets:
			return "Calibration view: no frames checked."
		parts = ["{} {:,} views ({:.0f}% covered)".format(n, c.views, 100 * c.Covered())
			for n, c in zip(self.names, self.coverage)]
		pairs = ["{}-{} {:,}".format(self.names[i], self.names[j], int(self.pairs[i, j]))
			for i in range(len(self.names)) for j in range(i + 1, len(self.names))]
		text = "Calibration view: {:,} frame sets checked ({:.0f} ms each); {}. Frames seen by both cameras: {}. "\
			"Detection used {:.0f}% of one core.".format(self.sets, 1000 * self.busy / self.sets, ", ".join(parts),
			", ".join(pairs) or "-", 100 * self.CpuShare())
		if self.detector is not None and self.board.get("preset") == boards.AUTO:
			text += " Board: " + (self.detector.reason or self.detector.status)
		return text

	def Result(self):
		"""For campy-acquire's main process (campy/calibrate.py): the board found, and the counts."""
		d = self.detector
		return {
			"board": d.Found() if d is not None else None,
			"status": d.status if d is not None else None,
			"reason": (d.reason if d is not None else self.problem) or "",
			"candidates": [p["id"] for p in d.candidates] if d is not None else [],
			"views": {n: c.views for n, c in zip(self.names, self.coverage)},
			}

	# ------------------------------------------------------------ drawing (Window.overlays)

	def Overlay(self, painter, camera, message):
		if not self.on:
			return
		from PyQt5 import QtCore, QtGui
		px = 1.0 / max(1e-6, painter.transform().m11()) # one widget pixel, in the frame's pixels
		with self.lock:
			cells = self.coverage[camera].cells.copy()
			latest = self.latest[camera]
		image = message.get("image") if message else None
		if image is not None:
			h, w = np.asarray(image).shape[:2]
			cw, ch = w / COVER[0], h / COVER[1]
			top = max(1, int(cells.max()))
			for y, x in zip(*np.nonzero(cells)):
				alpha = int(30 + 50 * min(1.0, cells[y, x] / max(3, top / 2)))
				painter.fillRect(QtCore.QRectF(x * cw, y * ch, cw, ch), QtGui.QColor(60, 220, 90, alpha))
		if latest is not None and time.monotonic() - latest[0] < SHOW_S:
			_, _, corners, markers = latest
			painter.setPen(QtGui.QPen(QtGui.QColor(0, 220, 255), 1.5 * px))
			for m in markers if not len(corners) else ():
				painter.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(float(x), float(y)) for x, y in m]))
			painter.setPen(Qt().NoPen)
			painter.setBrush(QtGui.QColor(255, 220, 0))
			r = 3 * px
			for x, y in corners:
				painter.drawEllipse(QtCore.QPointF(float(x), float(y)), r, r)
			painter.setBrush(Qt().NoBrush)
		self.DrawLines(painter, self.Lines(camera))

	@staticmethod
	def DrawLines(painter, lines):
		# At the frame's bottom left, in the widget's pixels (the painter is in the frame's)
		from PyQt5 import QtCore, QtGui
		box = painter.transform().mapRect(painter.clipBoundingRect())
		painter.save()
		painter.resetTransform()
		font = painter.font()
		font.setPixelSize(max(10, min(14, int(box.height() / 22))))
		painter.setFont(font)
		metrics = QtGui.QFontMetrics(font)
		line = metrics.height() + 3
		colours = {"good": QtGui.QColor(70, 200, 90), "bad": QtGui.QColor(255, 90, 80), "text": QtGui.QColor(235, 235, 235)}
		y = box.bottom() - 6 - line * len(lines)
		for text, colour in lines:
			text = metrics.elidedText(text, Qt().ElideRight, int(box.width() - 20))
			rect = QtCore.QRectF(box.left() + 6, y, metrics.horizontalAdvance(text) + 8, line)
			painter.fillRect(rect, QtGui.QColor(0, 0, 0, 170))
			painter.setPen(colours[colour])
			painter.drawText(rect, Qt().AlignCenter, text)
			y += line
		painter.restore()


def Qt():
	from PyQt5 import QtCore
	return QtCore.Qt


def Attach(window, info):
	"""
	Adds the calibration view to the one window: key c turns it on and off,
	and calibrationMode turns it on at the start. info: windowfeed.WindowInfo's
	"calibration". Returns the view.
	"""
	info = info or {}
	view = CalibrationView([t.name for t in window.tiles], info.get("board"), info.get("squareMm"))
	window.watchers.append(view.Take)
	window.overlays.append(view.Overlay)

	def Toggle():
		view.Toggle()
		print("Calibration view {}.".format("on" if view.on else "off"), flush=True)
	window.keys[Qt().Key_C] = Toggle
	if info.get("on"):
		view.Start()
	return view
