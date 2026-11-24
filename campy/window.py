"""
campy's one window (displayMode "one-window"): every camera side by side.

It runs in a process of its own, started by campy-acquire (campy/windowfeed.py),
at a lower priority than the cameras, and draws the frames the camera processes
send it. A camera never waits for it: if the window falls behind, or is closed,
the cameras skip the frames it has not taken and record on. It closes when the
recording ends.

Each camera's tile shows its name, frame number and a badge: its frame rate
(green), or what is wrong (red): SLOW (below 95 % of frameRate), DROPPED (gaps
in the camera's timestamps), ENCODER BEHIND (frames waiting to be written), NO
FRAMES (none for a few seconds, e.g. an unplugged camera, whose last frame
stays dimmed while the other cameras go on).

Mouse and keys:
	double click  one camera alone, and back to every camera
	wheel         zoom into a camera about the pointer; drag to move it
	0             the whole frame again
	1-9           camera 1-9 alone
	left, right   the previous or next camera, when one is alone
	g, Esc        every camera
	c             the calibration view: the board's corners, and where they have been seen (campy/calibview.py)

For modes like it, Window.overlays holds functions that draw over each camera's
frame, Window.keys maps keys to functions, and Window.watchers holds
functions that see every frame the window takes.
"""

import os, signal, sys, time, queue

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

POLL_MS = 15 # how often the queues are read
BADGE_EVERY_S = 0.25 # badges are drawn again at least this often, frames or not
STALL_S = 3.0 # a camera without a new frame for this long: NO FRAMES
RATE_WINDOW_S = 2.0 # the frame rate is counted over this long
SLOW = 0.95 # a camera below this share of its frameRate: SLOW
BEHIND_S = 1.0 # frames waiting to be written for over this long: ENCODER BEHIND
ZOOM_STEP, ZOOM_MOST = 1.15, 16.0
SCREEN_SHARE = 0.9 # the window opens at most this share of the screen
GOOD, BAD, QUIET = QtGui.QColor(70, 200, 90), QtGui.QColor(220, 50, 40), QtGui.QColor(150, 150, 150)


def Grid(n, frameSize, area):
	"""
	The columns and rows that show n frames of frameSize (width, height) the
	largest in area (width, height), and each tile's size (width, height).
	"""
	fw, fh = max(1, frameSize[0]), max(1, frameSize[1])
	best = None
	for cols in range(1, max(1, n) + 1):
		rows = -(-max(1, n) // cols)
		scale = min(area[0] / (cols * fw), area[1] / (rows * fh))
		empty = cols * rows - n
		key = (round(scale, 6), -empty, -cols)
		if best is None or key > best[0]:
			best = (key, cols, rows)
	_, cols, rows = best
	return cols, rows, (area[0] // cols, area[1] // rows)


def Fit(frameSize, box):
	"""The rectangle (x, y, width, height) of a frame of frameSize fitted in box (x, y, width, height), centred."""
	x, y, w, h = box
	scale = min(w / max(1, frameSize[0]), h / max(1, frameSize[1]))
	fw, fh = frameSize[0] * scale, frameSize[1] * scale
	return x + (w - fw) / 2, y + (h - fh) / 2, fw, fh


class Health:
	"""
	One camera's frame rate and problems, from the frames it sends: their
	frame numbers and camera timestamps, and how many frames wait to be
	written (queued).
	"""

	def __init__(self, frameRate=0.0):
		self.frameRate = frameRate
		self.samples = [] # (arrival, frame number, camera timestamp)
		self.dropped = 0
		self.queued = 0
		self.ended = False
		self.last = None

	def Add(self, frameNumber, timeStamp, queued, now):
		if self.samples and frameNumber is not None and timeStamp is not None:
			_, n0, t0 = self.samples[-1]
			dn, dt = frameNumber - n0, timeStamp - t0
			if dn > 0 and dt > 0 and self.frameRate > 0:
				# Frames the camera's clock says it took, and campy did not get
				self.dropped += max(0, int(round(dt * self.frameRate)) - dn)
		if frameNumber is not None and timeStamp is not None:
			self.samples.append((now, frameNumber, timeStamp))
		self.samples = [s for s in self.samples if s[0] >= now - RATE_WINDOW_S]
		self.queued = queued or 0
		self.last = now

	def Rate(self):
		if len(self.samples) < 2:
			return None
		(_, n0, t0), (_, n1, t1) = self.samples[0], self.samples[-1]
		return (n1 - n0) / (t1 - t0) if t1 > t0 else None

	def Badge(self, now):
		"""The badge's text, and whether it says something is wrong."""
		if self.ended:
			return "ENDED", False
		if self.last is None:
			return "WAITING", False
		if now - self.last > STALL_S:
			return "NO FRAMES {:.0f} s".format(now - self.last), True
		problems = []
		rate = self.Rate()
		counted = self.samples[-1][2] - self.samples[0][2] if self.samples else 0
		if rate is not None and self.frameRate > 0 and counted >= 1.0 and rate < SLOW * self.frameRate:
			problems.append("SLOW")
		if self.dropped:
			problems.append("{:,} DROPPED".format(self.dropped))
		if self.frameRate > 0 and self.queued / self.frameRate > BEHIND_S:
			problems.append("ENCODER {:.1f} s BEHIND".format(self.queued / self.frameRate))
		text = "{:.1f} fps".format(rate) if rate is not None else ""
		return "  ".join([text] + problems).strip(), bool(problems)


class Zoom:
	"""
	A camera's zoom: how many times its fit it is shown, about which pixel
	of the frame (its centre at first). Kept between the grid and the camera
	alone.
	"""

	def __init__(self):
		self.times, self.centre = 1.0, None

	def Source(self, frameSize):
		# The part of the frame shown: (x, y, width, height), in the frame's pixels
		w, h = frameSize[0] / self.times, frameSize[1] / self.times
		cx, cy = self.centre if self.centre is not None else (frameSize[0] / 2, frameSize[1] / 2)
		x = min(max(0.0, cx - w / 2), frameSize[0] - w)
		y = min(max(0.0, cy - h / 2), frameSize[1] - h)
		self.centre = (x + w / 2, y + h / 2)
		return x, y, w, h

	def About(self, factor, at, frameSize, target):
		# factor times nearer, the frame's pixel under at (a widget point) staying under it
		x, y, w, h = self.Source(frameSize)
		tx, ty, tw, th = target
		fx = x + (at[0] - tx) / tw * w
		fy = y + (at[1] - ty) / th * h
		self.times = min(max(1.0, self.times * factor), ZOOM_MOST)
		w, h = frameSize[0] / self.times, frameSize[1] / self.times
		self.centre = (fx - (at[0] - tx) / tw * w + w / 2, fy - (at[1] - ty) / th * h + h / 2)
		self.Source(frameSize)

	def Pan(self, dx, dy, frameSize, target):
		# Dragged by dx, dy widget pixels: the frame moves with the mouse
		x, y, w, h = self.Source(frameSize)
		self.centre = (x + w / 2 - dx * w / target[2], y + h / 2 - dy * h / target[3])
		self.Source(frameSize)

	def Reset(self):
		self.times, self.centre = 1.0, None


class Tile:
	"""One camera in the window: its newest frame, its health, and its zoom."""

	def __init__(self, name):
		self.name = name
		self.message = None # the newest frame's message from windowfeed.Feed
		self.image = None # it, as a QImage (holding the frame's array)
		self.health = Health()
		self.zoom = Zoom()
		self.shown = 0

	def Take(self, message, now):
		self.name = message.get("name", self.name)
		self.health.frameRate = message.get("frameRate", self.health.frameRate)
		if message.get("ended"):
			self.health.ended = True
			return
		self.health.Add(message.get("frameNumber"), message.get("timeStamp"), message.get("queued"), now)
		self.message = message
		self.image = Image(message["image"])
		self.shown += 1

	def FrameSize(self):
		return (self.image.width(), self.image.height()) if self.image is not None else None


def Image(img):
	"""A frame (height x width, or x 1 or 3 channels) as a QImage that holds its array."""
	img = np.asarray(img)
	if img.dtype != np.uint8:
		img = (img.astype(np.float64) * (255.0 / max(1, np.iinfo(img.dtype).max if img.dtype.kind in "ui" else 1)))\
			.clip(0, 255).astype(np.uint8)
	if img.ndim == 3 and img.shape[2] == 1:
		img = img[:, :, 0]
	img = np.ascontiguousarray(img)
	h, w = img.shape[:2]
	if img.ndim == 2:
		image = QtGui.QImage(img.data, w, h, img.strides[0], QtGui.QImage.Format_Grayscale8)
	else:
		image = QtGui.QImage(img.data, w, h, img.strides[0], QtGui.QImage.Format_RGB888)
	image.array = img # the QImage does not copy the pixels
	return image


class Window(QtWidgets.QWidget):
	"""
	Every camera's tile in a grid, or one camera alone. overlays: functions
	f(painter, camera, message) drawing over each camera's frame, the painter
	in the frame's (displayed) pixels and clipped to it. keys: Qt key ->
	function of no arguments. watchers: functions f(camera, message) called
	with every frame message the window takes.
	"""

	def __init__(self, cameraQueues, info, stop=None):
		super().__init__()
		self.queues = cameraQueues
		self.stop = stop
		names = info.get("names") or ["Camera{}".format(n) for n in range(len(cameraQueues))]
		self.tiles = [Tile(name) for name in names]
		self.frameSize = tuple(info.get("frameSize") or (640, 480))
		self.alone = None # the camera shown alone, or None: every camera
		self.drag = None
		self.lastBadges = 0.0
		self.overlays = []
		self.watchers = []
		self.keys = {Qt.Key_G: self.ShowAll, Qt.Key_Escape: self.ShowAll, Qt.Key_0: self.ResetZoom,
			Qt.Key_Left: lambda: self.Step(-1), Qt.Key_Right: lambda: self.Step(1)}
		for k in range(min(9, len(self.tiles))):
			self.keys[Qt.Key_1 + k] = lambda k=k: self.ShowAlone(k)
		self.setWindowTitle("campy: {} cameras".format(len(self.tiles)))
		self.setAttribute(Qt.WA_OpaquePaintEvent)
		self.setMouseTracking(True)
		self.setFocusPolicy(Qt.StrongFocus)
		self.setMinimumSize(320, 240)
		self.resize(*self.FitScreen())
		self.timer = QtCore.QTimer(self)
		self.timer.timeout.connect(self.Poll)
		self.timer.start(POLL_MS)

	def FitScreen(self):
		# Every camera at its frames' size, laid out for the screen, and smaller if need be to fit on it
		screen = QtWidgets.QApplication.primaryScreen()
		area = screen.availableGeometry() if screen is not None else QtCore.QRect(0, 0, 1600, 900)
		area = (SCREEN_SHARE * area.width(), SCREEN_SHARE * area.height())
		cols, rows, _ = Grid(len(self.tiles), self.frameSize, area)
		width, height = cols * self.frameSize[0], rows * self.frameSize[1]
		scale = min(1.0, area[0] / width, area[1] / height)
		return max(320, int(width * scale)), max(240, int(height * scale))

	# ------------------------------------------------------------ frames in

	def Poll(self):
		if self.stop is not None and self.stop.is_set():
			self.close()
			return
		now = time.monotonic()
		changed = False
		for q in self.queues:
			while True:
				try:
					message = q.get_nowait()
				except queue.Empty:
					break
				except (EOFError, OSError, ValueError):
					break
				camera = message.get("camera", 0)
				if 0 <= camera < len(self.tiles):
					self.tiles[camera].Take(message, now)
					for watch in self.watchers:
						watch(camera, message)
					changed = True
		if changed or now - self.lastBadges > BADGE_EVERY_S:
			self.lastBadges = now
			self.update()

	# ------------------------------------------------------------ layout

	def Shown(self):
		return [self.alone] if self.alone is not None else list(range(len(self.tiles)))

	def Boxes(self):
		# Each camera shown, and its tile's box (x, y, width, height) in the widget
		shown = self.Shown()
		sizes = [self.tiles[c].FrameSize() for c in shown if self.tiles[c].FrameSize()]
		frameSize = max(sizes, key=lambda s: s[0] * s[1]) if sizes else self.frameSize
		cols, rows, (tw, th) = Grid(len(shown), frameSize, (self.width(), self.height()))
		x0 = (self.width() - cols * tw) // 2
		y0 = (self.height() - rows * th) // 2
		return [(c, (x0 + (k % cols) * tw, y0 + (k // cols) * th, tw, th)) for k, c in enumerate(shown)]

	def Target(self, c, box):
		# Where camera c's frame is drawn in its box, or None before its first frame
		size = self.tiles[c].FrameSize()
		return Fit(size, box) if size else None

	def CameraAt(self, x, y):
		for c, (bx, by, bw, bh) in self.Boxes():
			if bx <= x < bx + bw and by <= y < by + bh:
				return c, (bx, by, bw, bh)
		return None, None

	# ------------------------------------------------------------ drawing

	def paintEvent(self, event):
		painter = QtGui.QPainter(self)
		painter.fillRect(self.rect(), Qt.black)
		now = time.monotonic()
		for c, box in self.Boxes():
			self.DrawTile(painter, c, box, now)
		painter.end()

	def DrawTile(self, painter, c, box, now):
		tile = self.tiles[c]
		target = self.Target(c, box)
		text, bad = tile.health.Badge(now)
		stale = tile.health.ended or (tile.health.last is not None and now - tile.health.last > STALL_S)
		if target is not None:
			size = tile.FrameSize()
			sx, sy, sw, sh = tile.zoom.Source(size)
			# Smooth, but each pixel sharp once zoomed in twice its size or more
			painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, tile.zoom.times == 1 or target[2] / sw < 2)
			painter.drawImage(QtCore.QRectF(*target), tile.image, QtCore.QRectF(sx, sy, sw, sh))
			if stale:
				painter.fillRect(QtCore.QRectF(*target), QtGui.QColor(0, 0, 0, 150))
			if self.overlays:
				painter.save()
				painter.setClipRect(QtCore.QRectF(*target))
				painter.translate(target[0], target[1])
				painter.scale(target[2] / sw, target[3] / sh)
				painter.translate(-sx, -sy)
				for overlay in self.overlays:
					overlay(painter, c, tile.message)
				painter.restore()
		if bad:
			painter.setPen(QtGui.QPen(BAD, 3))
			painter.drawRect(QtCore.QRectF(box[0] + 1.5, box[1] + 1.5, box[2] - 3, box[3] - 3))
		self.DrawLabels(painter, tile, box, text, bad)

	def DrawLabels(self, painter, tile, box, badge, bad):
		# The name and frame number at the top left; the badge at the top right, or under them if it would cover them
		x, y, w, h = box
		font = painter.font()
		font.setPixelSize(max(11, min(16, int(h / 20))))
		painter.setFont(font)
		metrics = QtGui.QFontMetrics(font)
		name = tile.name
		if tile.message is not None and tile.message.get("frameNumber") is not None:
			name += "  frame {:,}".format(tile.message["frameNumber"])
		if tile.zoom.times > 1:
			name += "  x{:.1f}".format(tile.zoom.times)
		pad, line = 6, metrics.height() + 4
		nameBox = QtCore.QRect(x + pad, y + pad, metrics.horizontalAdvance(name) + 8, line)
		self.Label(painter, nameBox, name, QtGui.QColor(235, 235, 235), QtGui.QColor(0, 0, 0, 170))
		if badge:
			width = metrics.horizontalAdvance(badge) + 8
			badgeBox = QtCore.QRect(x + w - pad - width, y + pad, width, line)
			if badgeBox.left() < nameBox.right() + pad:
				badgeBox.moveTop(nameBox.bottom() + 3)
			if bad:
				self.Label(painter, badgeBox, badge, Qt.white, BAD)
			else:
				self.Label(painter, badgeBox, badge, GOOD if badge.endswith("fps") else QUIET, QtGui.QColor(0, 0, 0, 170))

	@staticmethod
	def Label(painter, rect, text, color, background):
		painter.fillRect(rect, background)
		painter.setPen(QtGui.QColor(color))
		painter.drawText(rect, Qt.AlignCenter, text)

	# ------------------------------------------------------------ mouse and keys

	def wheelEvent(self, event):
		at = event.pos()
		c, box = self.CameraAt(at.x(), at.y())
		target = self.Target(c, box) if c is not None else None
		if target is None:
			return
		steps = event.angleDelta().y() / 120
		self.tiles[c].zoom.About(ZOOM_STEP ** steps, (at.x(), at.y()), self.tiles[c].FrameSize(), target)
		self.update()

	def mousePressEvent(self, event):
		if event.button() == Qt.LeftButton:
			self.drag = (event.x(), event.y())

	def mouseMoveEvent(self, event):
		if self.drag is None or not (event.buttons() & Qt.LeftButton):
			return
		c, box = self.CameraAt(*self.drag)
		target = self.Target(c, box) if c is not None else None
		if target is not None:
			self.tiles[c].zoom.Pan(event.x() - self.drag[0], event.y() - self.drag[1], self.tiles[c].FrameSize(), target)
			self.update()
		self.drag = (event.x(), event.y())

	def mouseReleaseEvent(self, event):
		self.drag = None

	def mouseDoubleClickEvent(self, event):
		c, _ = self.CameraAt(event.x(), event.y())
		if self.alone is not None:
			self.ShowAll()
		elif c is not None:
			self.ShowAlone(c)

	def keyPressEvent(self, event):
		action = self.keys.get(event.key())
		if action is not None:
			action()
			self.update()
		else:
			super().keyPressEvent(event)

	def ShowAll(self):
		self.alone = None

	def ShowAlone(self, c):
		self.alone = c

	def Step(self, by):
		if self.alone is not None:
			self.alone = (self.alone + by) % len(self.tiles)

	def ResetZoom(self):
		for c in self.Shown():
			self.tiles[c].zoom.Reset()

	def Summary(self):
		return "The camera window showed " + ", ".join("{} {:,} frames".format(t.name, t.shown) for t in self.tiles) + "."


def LowerPriority():
	# Below the camera processes, which must keep up
	try:
		if sys.platform == "win32":
			import ctypes
			kernel32 = ctypes.windll.kernel32
			kernel32.GetCurrentProcess.restype = ctypes.c_void_p
			kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
			kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x4000) # BELOW_NORMAL_PRIORITY_CLASS
		else:
			os.nice(10)
	except Exception:
		pass


def Run(cameraQueues, stop, info, results=None):
	"""
	The window's process (windowfeed.WindowProcess): shows the cameras until
	stop is set or the window is closed. Then puts what the calibration view
	found (calibview.CalibrationView.Result) in results.
	"""
	signal.signal(signal.SIGINT, signal.SIG_IGN) # Ctrl-C stops the cameras; the window closes after them
	LowerPriority()
	result = None
	try:
		app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([sys.argv[0]])
		window = Window(cameraQueues, info, stop)
		from campy import calibview
		calibration = calibview.Attach(window, info.get("calibration"))
		window.show()
		app.exec_()
		calibration.Close()
		print(window.Summary(), flush=True)
		if calibration.sets or calibration.problem:
			print(calibration.Summary(), flush=True)
			result = calibration.Result()
	except Exception as e:
		print("The camera window could not run: {}. The recording goes on without it.".format(e), flush=True)
		raise
	finally:
		if results is not None:
			results.put(result)
