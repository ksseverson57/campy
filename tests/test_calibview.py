"""The calibration view over the one window, on ChArUco frames rendered with OpenCV."""

import os, queue, time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
if not hasattr(cv2.aruco, "CharucoDetector"):
	pytest.skip("needs OpenCV 4.7 or newer", allow_module_level=True)

from campy import calibview, window
from campy.utils import boards
from PyQt5 import QtCore, QtGui, QtWidgets

BOARD = boards.Board("CCT300200C") # 14 x 9 squares: 13 x 8 = 104 corners


def Frame(where=(0.15, 0.15, 0.85, 0.85), size=(640, 480), tilt=0.08, grey=False):
	"""A camera frame (RGB) showing calib.io's 300 x 200 coarse board, with its corners at where (fractions)."""
	d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
	board = cv2.aruco.CharucoBoard((14, 9), 20.0, 15.0, d)
	img = board.generateImage((1400, 900), marginSize=0, borderBits=1)
	img = cv2.copyMakeBorder(img, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
	h, w = img.shape
	x0, y0, x1, y1 = [v * s for v, s in zip(where, size * 2)]
	dst = np.float32([[x0, y0 + tilt * (y1 - y0)], [x1, y0], [x1, y1], [x0, y1 - tilt * (y1 - y0)]])
	frame = cv2.warpPerspective(img, cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), dst),
		size, borderValue=90)
	return frame if grey else cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)


def Message(camera, image, frameNumber=3):
	return dict(camera=camera, name="Camera{}".format(camera), frameRate=30.0, image=image, frameNumber=frameNumber,
		timeStamp=frameNumber / 30.0, queued=0)


def View(n=2, board=BOARD, **kw):
	view = calibview.CalibrationView(["Camera{}".format(c) for c in range(n)], board, threaded=False, **kw)
	view.Start()
	return view


def test_the_corners_are_found_in_every_camera_and_the_pair_counted():
	view = View(3)
	frame = Frame()
	view.Take(0, Message(0, frame))
	view.Take(1, Message(1, Frame((0.3, 0.2, 0.95, 0.7), grey=True))) # a mono camera
	view.Take(2, Message(2, np.full((480, 640, 3), 90, np.uint8))) # no board in view
	assert view.Step() == 3
	assert len(view.latest[0][2]) > 95 and len(view.latest[1][2]) > 95 and len(view.latest[2][2]) == 0 # of 104
	assert [c.views for c in view.coverage] == [1, 1, 0]
	assert view.pairs.tolist() == [[0, 1, 0], [1, 0, 0], [0, 0, 0]]
	# The corners are where the board is drawn
	xs, ys = view.latest[0][2][:, 0], view.latest[0][2][:, 1]
	assert 0.15 * 640 < xs.min() and xs.max() < 0.85 * 640 and 0.15 * 480 < ys.min() and ys.max() < 0.85 * 480
	assert view.Step() == 0 # nothing new


def test_coverage_fills_where_the_board_has_been():
	view = View(1)
	view.Take(0, Message(0, Frame((0.02, 0.05, 0.48, 0.5)), 3))
	view.Step()
	cells = view.coverage[0].cells
	assert cells[:, calibview.COVER[0] // 2 + 1:].sum() == 0 and cells[calibview.COVER[1] // 2 + 1:].sum() == 0
	first = view.coverage[0].Covered()
	assert 0.05 < first < 0.3
	view.Take(0, Message(0, Frame((0.52, 0.5, 0.98, 0.95)), 6))
	view.Step()
	assert view.coverage[0].Covered() > 1.8 * first and view.coverage[0].views == 2


def test_cameras_are_detected_on_the_same_frame_number():
	view = View(2)
	frame = Frame()
	view.Take(0, Message(0, frame, 3))
	view.Take(0, Message(0, frame, 6))
	view.Take(1, Message(1, frame, 3))
	assert view.Next()[0] == 3 # the frame both cameras have, though camera 0 has a newer one
	assert view.Next() == (None, {}) # frame 6 waits for camera 1
	view.Take(1, Message(1, frame, 6))
	number, images = view.Next()
	assert number == 6 and sorted(images) == [0, 1]
	view.Take(0, Message(0, frame, 9))
	view.Take(0, Message(0, frame, 12)) # camera 1 sends no frame 9: it goes alone once frame 12 has come
	number, images = view.Next()
	assert number == 9 and list(images) == [0]


def test_frames_wait_in_a_short_line_and_a_slow_detector_skips_them():
	view = calibview.CalibrationView(["Camera0", "Camera1"], BOARD, every=0.0)
	view.Start()

	class Slow:
		def Detect(self, image):
			time.sleep(0.3)
			return np.zeros((0, 2)), []
	view.detector = Slow()
	frame = Frame()
	t0 = time.perf_counter()
	for n in range(0, 300, 3):
		for c in range(2):
			view.Take(c, Message(c, frame, n))
	took = time.perf_counter() - t0
	assert took < 0.5 # the window's thread never waits for detection
	assert all(len(p) <= calibview.PENDING for p in view.pending)
	time.sleep(0.5)
	view.Close()
	assert view.sets <= 3 # the rest were skipped


def test_auto_identifies_a_calibio_board_then_finds_its_corners():
	view = View(2, board=None, squareMm=20)
	frames = [Frame((0.1, 0.1, 0.9, 0.85)), Frame((0.2, 0.15, 0.8, 0.7), tilt=-0.1)]
	n = 0
	while view.detector.status != "match" and n < 60:
		n += 3
		for c in range(2):
			view.Take(c, Message(c, frames[c], n))
		view.Step()
	assert view.detector.status == "match", view.detector.reason
	assert view.latest[0][2].shape == (0, 2) and len(view.latest[0][3]) > 20 # markers shown until then
	for c in range(2):
		view.Take(c, Message(c, frames[c], n + 3))
	view.Step()
	assert len(view.latest[0][2]) > 95
	result = view.Result()
	assert result["board"]["preset"] == "calibio-300x200-coarse" and result["status"] == "match"
	assert any("calib.io 300 x 200 mm coarse" in t for t, _ in view.Lines(0))


def test_auto_without_the_size_finds_the_corners_and_says_the_size_is_missing():
	view = View(1, board=None)
	frame = Frame()
	for n in range(3, 40, 3):
		view.Take(0, Message(0, frame, n))
		view.Step()
	assert view.detector.status == "size-ambiguous"
	assert len(view.latest[0][2]) > 95
	assert view.Result()["candidates"] == ["calibio-600x400-coarse", "calibio-300x200-coarse"]
	assert "set calibrationSquareMm" in view.Lines(0)[-1][0]


def test_without_opencv_the_tiles_say_what_to_install():
	view = calibview.CalibrationView(["Camera0"], BOARD, loader=lambda: (None, "needs OpenCV 4.7 or newer: pip "
		"install opencv-python"), threaded=False)
	view.Start()
	view.Take(0, Message(0, Frame()))
	assert view.Lines(0) == [("CALIBRATION needs OpenCV 4.7 or newer: pip install opencv-python", "bad")]
	assert "pip install opencv-python" in view.Summary() and view.Result()["board"] is None


def test_the_real_loader_finds_opencv():
	cv, problem = calibview.LoadCv2()
	assert cv is cv2 and problem is None


# ------------------------------------------------------------------ in the window

@pytest.fixture(scope="module")
def app():
	return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def Pixel(image, x, y):
	c = QtGui.QColor(image.pixel(int(x), int(y)))
	return c.red(), c.green(), c.blue()


def test_key_c_turns_the_view_on_and_it_draws_over_each_camera(app, tmp_path):
	queues = [queue.Queue() for _ in range(4)]
	w = window.Window(queues, {"names": ["back", "mid", "side", "top"], "frameSize": (640, 480)})
	w.timer.stop()
	w.resize(1280, 960)
	view = calibview.Attach(w, {"board": BOARD})
	assert not view.on
	w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_C, QtCore.Qt.NoModifier))
	assert view.on
	places = [(0.1, 0.1, 0.6, 0.55), (0.35, 0.3, 0.9, 0.8), (0.05, 0.4, 0.5, 0.9), None]
	deadline = time.monotonic() + 10
	n = 0
	while view.sets < 6 and time.monotonic() < deadline:
		n += 3
		for c, where in enumerate(places):
			shift = 0.04 * (n % 9) / 3
			image = Frame((where[0] + shift, where[1], where[2] + shift, where[3])) if where else \
				np.full((480, 640, 3), 90, np.uint8)
			queues[c].put(Message(c, image, n))
		w.Poll()
		time.sleep(0.25)
	assert view.sets >= 6
	shot = w.grab().toImage().convertToFormat(QtGui.QImage.Format_RGB32)
	boxes = dict(w.Boxes())
	tx, ty, tw, th = w.Target(0, boxes[0])
	corners = view.latest[0][2]
	x, y = corners[0]
	r, g, b = Pixel(shot, tx + x * tw / 640, ty + y * th / 480)
	assert r > 200 and g > 180 and b < 100 # a yellow corner dot
	assert view.pairs[0, 1] > 0 and view.pairs[0, 3] == 0
	assert any(t.startswith("with mid") for t, _ in view.Lines(0))
	path = os.environ.get("CAMPY_CALIBRATION_PNG") or str(tmp_path / "calibration.png")
	assert shot.save(path)
	w.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_C, QtCore.Qt.NoModifier))
	assert not view.on
	view.Close()
	assert "Calibration view:" in view.Summary() and "one core" in view.Summary()


def test_calibration_mode_starts_the_view_on(app):
	w = window.Window([queue.Queue()], {"names": ["Camera0"], "frameSize": (640, 480)})
	w.timer.stop()
	view = calibview.Attach(w, {"board": BOARD, "on": True})
	assert view.on
	view.Close()


def test_the_window_info_carries_the_calibration_settings():
	from campy import windowfeed
	params = {"numCams": 2, "cameraNames": ["a", "b"], "frameWidth": 640, "frameHeight": 480, "displayDownsample": 2}
	assert windowfeed.WindowInfo(params)["calibration"] == {"board": None, "squareMm": None, "on": False}
	params.update(calibrationBoard="CCT300200C", calibrationMode=True)
	info = windowfeed.WindowInfo(params)["calibration"]
	assert info["board"] == BOARD and info["on"] is True
