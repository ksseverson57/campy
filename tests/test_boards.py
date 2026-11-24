"""calibrationBoard: calib.io's boards, the same as calibrat3's, board.toml, and telling the board from its markers."""

import os, re, subprocess

import numpy as np
import pytest

from campy.utils import boards


# ------------------------------------------------------------------ the presets, as calibrat3 has them

def Calibrat3Presets():
	"""
	calibrat3's calib/board-presets.js: from $CALIBRAT3 (a checkout), or from
	$CALIBRAT3_GIT's branch claude/calibio-board-presets. None if neither.
	"""
	path = os.path.join(os.environ.get("CALIBRAT3", ""), "calib", "board-presets.js")
	if os.environ.get("CALIBRAT3") and os.path.isfile(path):
		with open(path, encoding="utf-8") as f:
			return f.read()
	if os.environ.get("CALIBRAT3_GIT"):
		try:
			return subprocess.run(["git", "-C", os.environ["CALIBRAT3_GIT"], "show",
				os.environ.get("CALIBRAT3_REF", "origin/claude/calibio-board-presets") + ":calib/board-presets.js"],
				capture_output=True, text=True, check=True).stdout
		except (OSError, subprocess.CalledProcessError):
			return None
	return None


def ParsePresets(js):
	# preset('CCT800600C', [800, 600, 6], 'coarse', 'aluminium composite', 9, 12, 60, 45),
	n = r"([\d.]+)"
	pattern = re.compile(r"preset\('(\w+)',\s*\[{0},\s*{0},\s*{0}\],\s*'(\w+)',\s*'([^']+)',\s*{0},\s*{0},\s*{0},\s*{0}\)"
		.format(n))
	number = lambda s: float(s) if "." in s else int(s)
	out = []
	for m in pattern.finditer(js.split("export const CALIBIO_PRESETS", 1)[1]):
		sku, w, h, t, pattern_, material, rows, cols, square, marker = m.groups()
		out.append({"id": "calibio-{}x{}-{}".format(w, h, pattern_), "sku": sku, "plate": (int(w), int(h), int(t)),
			"pattern": pattern_, "material": material, "rows": int(rows), "cols": int(cols),
			"square_length": number(square), "marker_length": number(marker)})
	return out, js


def test_the_presets_are_calibrat3s_value_for_value():
	js = Calibrat3Presets()
	if js is None:
		pytest.skip("calibrat3's calib/board-presets.js isn't here: set CALIBRAT3 to a checkout of its "
			"claude/calibio-board-presets branch (or CALIBRAT3_GIT to a clone)")
	theirs, js = ParsePresets(js)
	assert len(theirs) == len(re.findall(r"^\s*preset\('", js, re.M)) # every line parsed
	assert theirs == boards.PRESETS
	assert "CALIBIO_DICT = 'DICT_5X5_1000'" in js and "firstId: 0" in js and "legacyPattern: false" in js
	assert "id: `calibio-${w}x${h}-${pattern}`" in js # the ids are made as here


def test_every_preset_is_a_board_whose_markers_fit_its_dictionary():
	assert len({p["id"] for p in boards.PRESETS}) == len({p["sku"] for p in boards.PRESETS}) == 13
	for p in boards.PRESETS:
		board = boards.Board(p["sku"])
		assert board == boards.Board(p["id"].upper()) == boards.Board(" " + p["sku"].lower())
		assert boards.Board({k: board[k] for k in boards.BOARD_KEYS})["board_x"] == p["cols"] # a valid custom board too
		assert board["board_x"] > board["board_y"] # columns = squares across, the long side
		assert boards.MarkerCount(p["rows"], p["cols"]) <= 1000
		assert len(boards.MarkerSquares(p["rows"], p["cols"])) == boards.MarkerCount(p["rows"], p["cols"])


def test_the_labs_300_by_200_board():
	assert boards.Board("CCT300200C") == {"preset": "calibio-300x200-coarse", "board_x": 14, "board_y": 9,
		"square_length": 20, "marker_length": 15, "marker_bits": 5, "dict_size": 1000}


@pytest.mark.parametrize("spec,words", [
	("CCT999", "no calib.io board"),
	(12, "must be"),
	({"board_x": 5}, "missing"),
	({"board_x": 5, "board_y": 7, "square_length": 20, "marker_length": 25, "marker_bits": 4, "dict_size": 50},
		"smaller"),
	({"board_x": 5, "board_y": 7, "square_length": 20, "marker_length": 15, "marker_bits": 3, "dict_size": 50},
		"dictionary"),
	({"board_x": 20, "board_y": 20, "square_length": 20, "marker_length": 15, "marker_bits": 4, "dict_size": 50},
		"more than"),
	({"board_x": 5, "board_y": 7, "square_length": 20, "marker_length": 15, "marker_bits": 4, "dict_size": 50,
		"colour": 1}, "unknown"),
])
def test_a_wrong_board_says_why(spec, words):
	with pytest.raises(ValueError, match=words):
		boards.Board(spec)


def test_auto_and_none():
	assert boards.Board(None) is None
	assert boards.Board("Auto") == {"preset": "auto"}
	assert boards.Board("auto", 20) == {"preset": "auto", "square_length": 20}
	with pytest.raises(ValueError):
		boards.Board("auto", -1)


def test_board_toml():
	assert boards.BoardToml(boards.Board("CCT300200C")) == ('preset = "calibio-300x200-coarse"\nboard_x = 14\n'
		'board_y = 9\nsquare_length = 20\nmarker_length = 15\nmarker_bits = 5\ndict_size = 1000\n')
	assert boards.BoardToml(boards.Board("auto", 20)) == 'preset = "auto"\nsquare_length = 20\n'
	custom = {"board_x": 8, "board_y": 11, "square_length": 24.0, "marker_length": 18.75, "marker_bits": 4,
		"dict_size": 1000}
	text = boards.BoardToml(boards.Board(custom))
	assert "preset" not in text and "square_length = 24.0\n" in text and "marker_length = 18.75\n" in text


def test_board_toml_reads_back_in_sleap_aniposes_reader():
	tomllib = pytest.importorskip("tomllib")
	board = boards.Board("CCT600400F")
	assert tomllib.loads(boards.BoardToml(board)) == {"preset": "calibio-600x400-fine", "board_x": 28, "board_y": 17,
		"square_length": 20, "marker_length": 15, "marker_bits": 5, "dict_size": 1000}


# ------------------------------------------------------------------ which board, from its markers

cv2 = None


def Markers(preset, warp=None, part=None, size=(1400, 900)):
	"""DICT_5X5 markers detected on an image of preset's board (OpenCV)."""
	global cv2
	cv2 = pytest.importorskip("cv2")
	if not hasattr(cv2.aruco, "CharucoDetector"):
		pytest.skip("needs OpenCV 4.7 or newer")
	p = boards.PresetById(preset)
	d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
	board = cv2.aruco.CharucoBoard((p["cols"], p["rows"]), p["square_length"], p["marker_length"], d)
	img = board.generateImage(size, marginSize=40, borderBits=1)
	if part is not None:
		x0, y0, x1, y1 = part
		img = img[int(y0 * img.shape[0]):int(y1 * img.shape[0]), int(x0 * img.shape[1]):int(x1 * img.shape[1])]
		img = cv2.copyMakeBorder(img, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)
	if warp is not None:
		h, w = img.shape
		src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
		img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, np.float32(warp(w, h))), (w, h),
			borderValue=255)
	corners, ids, _ = cv2.aruco.ArucoDetector(d).detectMarkers(img)
	return ids.ravel().tolist(), [c.reshape(4, 2) for c in corners]


def test_a_whole_coarse_board_is_its_grid_and_the_square_size_picks_which():
	obs = [Markers("CCT300200C")]
	status, presets, why = boards.Identify(obs)
	assert status == "size-ambiguous" and {p["sku"] for p in presets} == {"CCT300200C", "CCT600400C"}, why
	status, presets, why = boards.Identify(obs, squareMm=20)
	assert status == "match" and presets[0]["sku"] == "CCT300200C", why
	status, presets, why = boards.Identify(obs, squareMm=40)
	assert status == "match" and presets[0]["sku"] == "CCT600400C", why


def test_a_board_sold_in_one_size_is_matched():
	status, presets, why = boards.Identify([Markers("CCT100075F", size=(2200, 1500))])
	assert status == "match" and presets[0]["sku"] == "CCT100075F", why


def test_part_of_a_tilted_board_upside_down():
	tilt = lambda w, h: [[w * 0.1, h * 0.05], [w * 0.95, h * 0.2], [w * 0.85, h * 0.9], [w * 0.02, h * 0.8]]
	upside_down = lambda w, h: [[w, h], [0, h], [0, 0], [w, 0]]
	for warp in (tilt, upside_down):
		obs = [Markers("CCT400300C", warp=warp, part=(0.1, 0.2, 0.7, 0.9))]
		status, presets, why = boards.Identify(obs, squareMm=30)
		assert status == "match" and presets[0]["sku"] == "CCT400300C", why


def test_too_few_markers_is_undecided_and_another_board_no_match():
	ids, corners = Markers("CCT300200C")
	assert boards.Identify([(ids[:3], corners[:3])])[0] == "undecided"
	# A 10 x 7 board of 5x5 markers, which calib.io doesn't sell
	d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
	img = cv2.aruco.CharucoBoard((10, 7), 20, 15, d).generateImage((1000, 700), marginSize=40, borderBits=1)
	c, i, _ = cv2.aruco.ArucoDetector(d).detectMarkers(img)
	status, presets, why = boards.Identify([(i.ravel().tolist(), [x.reshape(4, 2) for x in c])])
	assert status == "no-match" and not presets, why
