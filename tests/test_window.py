"""The one window (displayMode "one-window"): its layout, badges, zoom, and drawing, off screen."""

import os, queue, time

import numpy as np
import pytest

from campy import window
from PyQt5 import QtCore, QtGui, QtWidgets


# ---------------------------------------------------------------- layout

def BestScale(n, frame, area):
	return max(min(area[0] / (c * frame[0]), area[1] / (-(-n // c) * frame[1])) for c in range(1, n + 1))


@pytest.mark.parametrize("n", range(1, 13))
@pytest.mark.parametrize("area", [(1600, 900), (900, 1600), (1920, 1080), (640, 480)])
def test_the_grid_shows_the_frames_as_large_as_they_fit(n, area):
	frame = (640, 480)
	cols, rows, (tw, th) = window.Grid(n, frame, area)
	assert cols * rows >= n and cols * tw <= area[0] and rows * th <= area[1]
	assert (cols - 1) * rows < n # no empty column
	scale = min(area[0] / (cols * frame[0]), area[1] / (rows * frame[1]))
	assert scale == pytest.approx(BestScale(n, frame, area))


def test_four_cameras_on_a_wide_screen_are_two_by_two():
	assert window.Grid(4, (640, 480), (1600, 900))[:2] == (2, 2)
	assert window.Grid(3, (640, 480), (3000, 600))[:2] == (3, 1)
	assert window.Grid(1, (640, 480), (100, 100)) == (1, 1, (100, 100))


def test_a_frame_is_fitted_in_its_tile_centred():
	assert window.Fit((640, 480), (0, 0, 800, 800)) == (0, 100, 800, 600)
	assert window.Fit((480, 640), (10, 20, 800, 400)) == (260, 20, 300, 400)


# ---------------------------------------------------------------- health badge

def Steady(health, frames, rate=30.0, every=3, start=0.0, now0=100.0, queued=0):
	for n in range(every, frames + 1, every):
		health.Add(n, start + n / rate, queued, now0 + n / rate)
	return now0 + frames / rate


def test_a_camera_that_keeps_up_shows_its_frame_rate():
	health = window.Health(30.0)
	now = Steady(health, 90)
	assert health.Badge(now) == ("30.0 fps", False)


def test_frames_missing_from_the_cameras_clock_are_dropped():
	health = window.Health(30.0)
	now = Steady(health, 30)
	health.Add(36, 39 / 30, 0, now + 0.2) # frames 31-36 reached campy, but the camera's clock moved 9 frames
	text, bad = health.Badge(now + 0.2)
	assert bad and "3 DROPPED" in text


def test_a_camera_below_its_frame_rate_is_slow():
	health = window.Health(30.0)
	now = Steady(health, 90, rate=25.0)
	text, bad = health.Badge(now)
	assert bad and text.startswith("25.0 fps") and "SLOW" in text


def test_frames_waiting_for_the_encoder_show():
	health = window.Health(30.0)
	now = Steady(health, 30, queued=60)
	text, bad = health.Badge(now)
	assert bad and "ENCODER 2.0 s BEHIND" in text


def test_a_camera_without_frames_says_so_and_one_that_ended_is_quiet():
	health = window.Health(30.0)
	assert health.Badge(0.0) == ("WAITING", False)
	now = Steady(health, 30)
	assert health.Badge(now + window.STALL_S + 2) == ("NO FRAMES 5 s", True)
	health.ended = True
	assert health.Badge(now + 10) == ("ENDED", False)


# ---------------------------------------------------------------- zoom

def test_zooming_keeps_the_pixel_under_the_pointer():
	zoom = window.Zoom()
	frame, target = (640, 480), (100, 50, 320, 240) # shown at half size
	at = (180, 110) # over the frame's pixel (160, 120)
	zoom.About(2.0, at, frame, target)
	x, y, w, h = zoom.Source(frame)
	assert (w, h) == (320, 240)
	assert x + (at[0] - target[0]) / target[2] * w == pytest.approx(160)
	assert y + (at[1] - target[1]) / target[3] * h == pytest.approx(120)


def test_zoom_stays_on_the_frame_and_resets():
	zoom = window.Zoom()
	frame, target = (640, 480), (0, 0, 640, 480)
	zoom.About(4.0, (639, 479), frame, target)
	zoom.Pan(-10000, -10000, frame, target) # far past the bottom right corner
	assert zoom.Source(frame) == (480, 360, 160, 120)
	zoom.About(0.01, (0, 0), frame, target)
	assert zoom.Source(frame) == (0, 0, 640, 480)
	zoom.About(1000, (0, 0), frame, target)
	assert zoom.times == window.ZOOM_MOST
	zoom.Reset()
	assert zoom.Source(frame) == (0, 0, 640, 480)


# ---------------------------------------------------------------- the window, drawn off screen

@pytest.fixture(scope="module")
def app():
	return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def Message(camera, image, frameNumber=3, timeStamp=0.1, **more):
	return dict(camera=camera, name="Camera{}".format(camera), frameRate=30.0, image=image,
		frameNumber=frameNumber, timeStamp=timeStamp, queued=0, **more)


def Pixel(image, x, y):
	c = QtGui.QColor(image.pixel(int(x), int(y)))
	return c.red(), c.green(), c.blue()


def Centre(rect):
	x, y, w, h = rect
	return x + w / 2, y + h / 2


def Shot(widget):
	return widget.grab().toImage().convertToFormat(QtGui.QImage.Format_RGB32)


def MakeWindow(app, n=4):
	queues = [queue.Queue() for _ in range(n)]
	w = window.Window(queues, {"names": ["Camera{}".format(c) for c in range(n)], "frameSize": (160, 120)})
	w.timer.stop() # polled by hand here
	w.resize(800, 600)
	return w, queues


@pytest.mark.parametrize("n, frame", [(4, (640, 512)), (4, (160, 120)), (8, (576, 512)), (1, (2048, 1536))])
def test_the_window_opens_at_the_frames_size_or_smaller_to_fit_the_screen(app, n, frame):
	w = window.Window([queue.Queue() for _ in range(n)], {"frameSize": frame})
	w.timer.stop()
	area = QtWidgets.QApplication.primaryScreen().availableGeometry()
	width, height = w.FitScreen()
	assert width <= window.SCREEN_SHARE * area.width() + 1 and height <= window.SCREEN_SHARE * area.height() + 1
	cols, rows, _ = window.Grid(n, frame, (width, height))
	if cols * frame[0] <= window.SCREEN_SHARE * area.width() and rows * frame[1] <= window.SCREEN_SHARE * area.height():
		assert (width, height) == (cols * frame[0], rows * frame[1]) # one pixel for one when they fit
	else:
		assert max(width / (window.SCREEN_SHARE * area.width()), height / (window.SCREEN_SHARE * area.height())) > 0.99


def test_every_camera_is_drawn_in_its_own_tile(app):
	w, queues = MakeWindow(app)
	colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
	for c, colour in enumerate(colours):
		queues[c].put(Message(c, np.tile(np.array(colour, np.uint8), (120, 160, 1))))
	queues[3].put(Message(3, np.full((120, 160), 128, np.uint8))) # a mono camera
	w.Poll()
	shot = Shot(w)
	boxes = dict(w.Boxes())
	assert len(boxes) == 4
	for c, colour in enumerate(colours + [(128, 128, 128)]):
		assert Pixel(shot, *Centre(w.Target(c, boxes[c]))) == colour
	assert [t.shown for t in w.tiles] == [1, 1, 1, 1]
	assert "Camera0 1 frames" in w.Summary()


def test_only_the_newest_frame_of_each_camera_is_kept(app):
	w, queues = MakeWindow(app, 1)
	for n in range(5):
		queues[0].put(Message(0, np.full((120, 160, 3), n, np.uint8), frameNumber=3 * n, timeStamp=n / 10))
	w.Poll()
	assert w.tiles[0].message["frameNumber"] == 12
	assert queues[0].empty()


def test_a_camera_with_no_frames_is_dimmed_and_framed_in_red_while_the_others_go_on(app):
	w, queues = MakeWindow(app, 2)
	for c in range(2):
		queues[c].put(Message(c, np.full((120, 160, 3), 200, np.uint8)))
	w.Poll()
	w.tiles[1].health.last -= window.STALL_S + 1 # its last frame came 4 s ago
	queues[0].put(Message(0, np.full((120, 160, 3), 200, np.uint8), frameNumber=6, timeStamp=0.2))
	w.Poll()
	shot = Shot(w)
	boxes = dict(w.Boxes())
	live = Pixel(shot, *Centre(w.Target(0, boxes[0])))
	stale = Pixel(shot, *Centre(w.Target(1, boxes[1])))
	assert live == (200, 200, 200) and stale[0] < 120
	assert w.tiles[1].health.Badge(time.monotonic())[0].startswith("NO FRAMES")
	x, y, bw, bh = boxes[1]
	assert Pixel(shot, x + 2, y + bh // 2) == (window.BAD.red(), window.BAD.green(), window.BAD.blue())


def test_double_click_shows_one_camera_alone_and_keys_bring_back_every_camera(app):
	w, queues = MakeWindow(app, 3)
	for c in range(3):
		queues[c].put(Message(c, np.zeros((120, 160, 3), np.uint8)))
	w.Poll()
	x, y = Centre(dict(w.Boxes())[1])
	w.mouseDoubleClickEvent(QtGui.QMouseEvent(QtCore.QEvent.MouseButtonDblClick, QtCore.QPointF(x, y),
		QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
	assert [c for c, _ in w.Boxes()] == [1]
	assert w.Boxes()[0][1] == (0, 0, 800, 600)
	w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Right, QtCore.Qt.NoModifier))
	assert [c for c, _ in w.Boxes()] == [2]
	w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_G, QtCore.Qt.NoModifier))
	assert [c for c, _ in w.Boxes()] == [0, 1, 2]
	w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_1, QtCore.Qt.NoModifier))
	assert [c for c, _ in w.Boxes()] == [0]


def test_the_wheel_zooms_the_camera_under_the_pointer(app):
	w, queues = MakeWindow(app, 2)
	image = np.zeros((120, 160, 3), np.uint8)
	image[:60, :80] = (255, 255, 0) # the top left quarter yellow
	for c in range(2):
		queues[c].put(Message(c, image))
	w.Poll()
	box = dict(w.Boxes())[0]
	tx, ty, tw, th = w.Target(0, box)
	at = QtCore.QPoint(int(tx + tw / 4), int(ty + th / 4)) # the yellow quarter's middle
	for _ in range(10):
		w.wheelEvent(QtGui.QWheelEvent(QtCore.QPointF(at), QtCore.QPointF(at), QtCore.QPoint(0, 0),
			QtCore.QPoint(0, 120), QtCore.Qt.NoButton, QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False))
	assert w.tiles[0].zoom.times > 3 and w.tiles[1].zoom.times == 1
	shot = Shot(w)
	assert Pixel(shot, tx + 3, ty + 3) == (255, 255, 0) # all yellow now, to the tile's corner
	assert Pixel(shot, tx + tw - 3, ty + th - 3) == (255, 255, 0)
	w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_0, QtCore.Qt.NoModifier))
	assert w.tiles[0].zoom.times == 1


def test_overlays_draw_in_the_frames_pixels_over_each_camera(app):
	w, queues = MakeWindow(app, 2)
	for c in range(2):
		queues[c].put(Message(c, np.zeros((120, 160, 3), np.uint8), corners=[(40, 30)]))
	w.Poll()
	calls = []

	def Corners(painter, camera, message):
		calls.append(camera)
		for x, y in message["corners"]:
			painter.fillRect(QtCore.QRectF(x - 2, y - 2, 4, 4), QtGui.QColor(255, 0, 255))
	w.overlays.append(Corners)
	shot = Shot(w)
	assert sorted(calls) == [0, 1]
	for c, box in w.Boxes():
		tx, ty, tw, th = w.Target(c, box)
		assert Pixel(shot, tx + 40 * tw / 160, ty + 30 * th / 120) == (255, 0, 255)


def test_the_window_closes_when_the_recording_ends(app):
	w, queues = MakeWindow(app, 1)
	stop = type("Stop", (), {"is_set": lambda self: True})()
	w.stop = stop
	w.show()
	w.Poll()
	assert not w.isVisible()


def test_screenshot(app, tmp_path):
	# A picture of the window for people to look at (set CAMPY_WINDOW_PNG to keep it)
	w, queues = MakeWindow(app, 4)
	ramp = np.linspace(0, 255, 160).astype(np.uint8)
	for c in range(4):
		image = np.zeros((120, 160, 3), np.uint8)
		image[..., c % 3] = ramp
		image[40:80, 60:100] = 255
		queues[c].put(Message(c, image, frameNumber=300 + c, timeStamp=10.0))
		queues[c].put(Message(c, image, frameNumber=303 + c, timeStamp=10.1))
	w.Poll()
	w.tiles[1].zoom.About(3.0, Centre(w.Target(1, dict(w.Boxes())[1])), (160, 120), w.Target(1, dict(w.Boxes())[1]))
	w.tiles[2].health.last -= 10
	w.tiles[3].health.queued = 90
	path = os.environ.get("CAMPY_WINDOW_PNG") or str(tmp_path / "window.png")
	assert Shot(w).save(path)
