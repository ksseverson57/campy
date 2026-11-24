"""
ChArUco calibration boards (config calibrationBoard), for the calibration
view (campy/calibview.py) and for calibrating after a calibration recording
(campy/calibrate.py).

calibrationBoard is one of:
	- a calib.io stock board, by id ("calibio-300x200-coarse") or SKU
	  ("CCT300200C"), in any case: PRESETS below;
	- "auto": a calib.io board, identified from its markers (Identify), with
	  calibrationSquareMm as the size when calib.io sells the grid in several;
	- a dict with sleap-anipose's board.toml keys: board_x, board_y (squares
	  across and down), square_length, marker_length (any unit: the
	  calibration comes out in it), marker_bits, dict_size (the ArUco
	  dictionary, e.g. 5 and 1000 for DICT_5X5_1000).

PRESETS mirrors calibrat3's calib/board-presets.js (talmolab/calibrat3), id
for id and value for value (tests/test_boards.py compares them): calib.io's
ChArUco product page, https://calib.io/products/charuco-targets. Every stock
board is DICT_5X5_1000, its first marker is id 0, and calib.io's
"rows x columns" are board_y x board_x.

Only numpy and the standard library here: OpenCV is needed by the
calibration view alone.
"""

import math

CALIBIO_SOURCE = "https://calib.io/products/charuco-targets"
CALIBIO_BITS, CALIBIO_DICT_SIZE = 5, 1000 # DICT_5X5_1000
BOARD_KEYS = ("board_x", "board_y", "square_length", "marker_length", "marker_bits", "dict_size")
AUTO = "auto"


def _Preset(sku, plate, pattern, material, rows, cols, square, marker):
	return {
		"id": "calibio-{}x{}-{}".format(plate[0], plate[1], pattern),
		"sku": sku,
		"plate": plate, # width, height, thickness (mm)
		"pattern": pattern,
		"material": material,
		"rows": rows,
		"cols": cols,
		"square_length": square,
		"marker_length": marker,
		}


# calib.io's stock ChArUco targets, coarse first, largest first (as calibrat3 lists them)
PRESETS = [
	_Preset("CCT800600C", (800, 600, 6), "coarse", "aluminium composite", 9, 12, 60, 45),
	_Preset("CCT600400C", (600, 400, 6), "coarse", "aluminium composite", 9, 14, 40, 30),
	_Preset("CCT400300C", (400, 300, 6), "coarse", "aluminium composite", 9, 12, 30, 22),
	_Preset("CCT300200C", (300, 200, 6), "coarse", "aluminium composite", 9, 14, 20, 15),
	_Preset("CCT200150C", (200, 150, 6), "coarse", "aluminium composite", 9, 12, 15, 11),
	_Preset("CCT800600F", (800, 600, 6), "fine", "aluminium composite", 17, 24, 30, 22),
	_Preset("CCT600400F", (600, 400, 6), "fine", "aluminium composite", 17, 28, 20, 15),
	_Preset("CCT400300F", (400, 300, 6), "fine", "aluminium composite", 17, 24, 15, 11),
	_Preset("CCT300200F", (300, 200, 6), "fine", "aluminium composite", 17, 28, 10, 7),
	_Preset("CCT200150F", (200, 150, 6), "fine", "aluminium composite", 17, 24, 7.5, 5.5),
	_Preset("CCT150100F", (150, 100, 3), "fine", "ceramic", 15, 24, 5, 3.5),
	_Preset("CCT100075F", (100, 75, 3), "fine", "ceramic", 15, 22, 4, 3),
	_Preset("CCT075050F", (75, 50, 3), "fine", "ceramic", 15, 24, 2.5, 1.8),
	]


def PresetById(key):
	"""A preset by id or SKU, in any case, or None."""
	k = str(key).strip().lower()
	for p in PRESETS:
		if k == p["id"] or k == p["sku"].lower():
			return p
	return None


def Label(p):
	return "calib.io {} x {} mm {}{} ({} x {} squares of {} mm, {})".format(p["plate"][0], p["plate"][1],
		p["pattern"], " ceramic" if p["material"] == "ceramic" else "", p["rows"], p["cols"], p["square_length"],
		p["sku"])


def PresetBoard(p):
	"""A preset as a board (board.toml's keys, plus its id)."""
	return {"preset": p["id"], "board_x": p["cols"], "board_y": p["rows"], "square_length": p["square_length"],
		"marker_length": p["marker_length"], "marker_bits": CALIBIO_BITS, "dict_size": CALIBIO_DICT_SIZE}


def Board(spec, squareMm=None):
	"""
	The board calibrationBoard names (the module's doc), as a dict of
	board.toml's keys plus "preset" (a preset's id, "auto", or None for a
	custom board). For "auto", only "preset" and, with squareMm,
	"square_length". None when spec is None. Raises ValueError, saying why,
	on anything else.
	"""
	if spec is None:
		return None
	if isinstance(spec, dict):
		missing = [k for k in BOARD_KEYS if k not in spec]
		unknown = sorted(set(spec) - set(BOARD_KEYS))
		if missing or unknown:
			raise ValueError("calibrationBoard: a custom board needs exactly {} ({}{})".format(", ".join(BOARD_KEYS),
				"missing " + ", ".join(missing) if missing else "", ("; " if missing else "") + "unknown " +
				", ".join(unknown) if unknown else ""))
		board = {"preset": None}
		for k in BOARD_KEYS:
			v = spec[k]
			if isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0:
				raise ValueError("calibrationBoard: {} must be a number above 0, not {!r}".format(k, v))
			board[k] = v
		for k in ("board_x", "board_y", "marker_bits", "dict_size"):
			if board[k] != int(board[k]):
				raise ValueError("calibrationBoard: {} must be a whole number, not {!r}".format(k, board[k]))
			board[k] = int(board[k])
		if board["marker_length"] >= board["square_length"]:
			raise ValueError("calibrationBoard: marker_length ({}) must be smaller than square_length ({})".format(
				board["marker_length"], board["square_length"]))
		if board["marker_bits"] not in (4, 5, 6, 7) or board["dict_size"] not in (50, 100, 250, 1000):
			raise ValueError("calibrationBoard: no ArUco dictionary DICT_{0}X{0}_{1} (marker_bits 4-7, dict_size "
				"50, 100, 250 or 1000)".format(board["marker_bits"], board["dict_size"]))
		if board["board_x"] < 3 or board["board_y"] < 3:
			raise ValueError("calibrationBoard: a ChArUco board needs at least 3 x 3 squares")
		if MarkerCount(board["board_y"], board["board_x"]) > board["dict_size"]:
			raise ValueError("calibrationBoard: a {} x {} board has {} markers, more than DICT_{}X{}_{} holds".format(
				board["board_x"], board["board_y"], MarkerCount(board["board_y"], board["board_x"]),
				board["marker_bits"], board["marker_bits"], board["dict_size"]))
		return board
	if not isinstance(spec, str):
		raise ValueError("calibrationBoard must be a calib.io board's id or SKU, \"auto\", or a dict of the board's "
			"values, not {!r}".format(spec))
	if spec.strip().lower() == AUTO:
		board = {"preset": AUTO}
		if squareMm is not None:
			board["square_length"] = SquareHint(squareMm)
		return board
	p = PresetById(spec)
	if p is None:
		raise ValueError("calibrationBoard: no calib.io board {!r}. Known: auto, {}, or a dict of the board's values "
			"({})".format(spec, ", ".join("{} ({})".format(p["id"], p["sku"]) for p in PRESETS), ", ".join(BOARD_KEYS)))
	return PresetBoard(p)


def SquareHint(squareMm):
	if isinstance(squareMm, bool) or not isinstance(squareMm, (int, float)) or not squareMm > 0:
		raise ValueError("calibrationSquareMm must be a number above 0 (the board's square side, in mm), not {!r}"
			.format(squareMm))
	return squareMm


def DictName(board):
	return "DICT_{0}X{0}_{1}".format(board["marker_bits"], board["dict_size"])


def BoardToml(board):
	"""board.toml (sleap-anipose's keys; calibrat3 also reads "preset")."""
	lines = []
	if board.get("preset"):
		lines.append('preset = "{}"'.format(board["preset"]))
	for k in BOARD_KEYS:
		if k in board:
			lines.append("{} = {}".format(k, board[k]))
	return "\n".join(lines) + "\n"


def Describe(board):
	if board is None:
		return "no board"
	if board.get("preset") == AUTO:
		return "a calib.io board, identified from its markers" + (", {} mm squares".format(board["square_length"])
			if "square_length" in board else "")
	if board.get("preset"):
		return Label(PresetById(board["preset"]))
	return "{} x {} squares of {}, markers {}, {}".format(board["board_x"], board["board_y"], board["square_length"],
		board["marker_length"], DictName(board))


# ------------------------------------------------------------------ which calib.io board: from its markers

def MarkerCount(rows, cols):
	return (rows * cols) // 2


def MarkerSquares(rows, cols):
	"""
	Where each marker id sits on a rows x cols board: [(col, row)], row 0 at
	the top, OpenCV >= 4.6's layout (the top left square black; every calib.io
	board has odd rows, where the older layout is the same).
	"""
	return [(x, y) for y in range(rows) for x in range(cols) if y % 2 != x % 2]


IDENTIFY = {
	"minMarkers": 4, # an image with fewer markers is left out
	"neighbourRadius": 2.3, # markers this many squares apart in the image are a pair
	"agreeTol": 0.35, # a pair agrees with a grid when predicted within this many marker sides
	"fitFraction": 0.85, # a grid fits when this share of the pairs agrees
	"margin": 0.15, # ...and beats every grid with another column count by this much
	"minPairs": 12, # pairs needed before deciding
	"maxOutOfRange": 0.1, # ids past a grid's last marker that rule it out
	}


def Grids(presets=None):
	"""The distinct square grids among the presets: [{rows, cols, markers, rho, squares, presets}]."""
	grids = []
	for p in presets or PRESETS:
		g = next((g for g in grids if g["rows"] == p["rows"] and g["cols"] == p["cols"]), None)
		if g is None:
			g = {"rows": p["rows"], "cols": p["cols"], "markers": MarkerCount(p["rows"], p["cols"]), "presets": [],
				"squares": MarkerSquares(p["rows"], p["cols"])}
			grids.append(g)
		g["presets"].append(p)
	for g in grids:
		g["rho"] = sum(p["marker_length"] / p["square_length"] for p in g["presets"]) / len(g["presets"])
	return grids


def ScoreImage(ids, corners, grids, o=IDENTIFY):
	"""
	How well each grid explains one image's markers: [(pairs agreeing, pairs,
	ids past its end)]. ids: n marker ids; corners: n x 4 x 2, each marker's
	corners as OpenCV gives them (top left, top right, bottom right, bottom
	left as printed).

	Each marker's own square says which way the board's rows and columns run
	around it, and how big a square is there. For each pair of nearby
	markers, a grid predicts where the second is from the first's corners and
	the two ids' places on it. The board's real grid predicts every pair within
	a fraction of a marker; a grid with another number of columns misplaces
	every pair spanning two rows by a square or more. (A whole-board
	homography can't tell: a patch of a grid with the wrong column count is a
	sheared copy of the right one; the markers' own squares are not sheared.)
	This is calibrat3's calib/board-identify.js.
	"""
	n = len(ids)
	rho = sum(g["rho"] for g in grids) / len(grids)
	h = rho / 2
	frames = []
	for c in corners:
		(x0, y0), (x1, y1), (x2, y2), (x3, y3) = [(float(p[0]), float(p[1])) for p in c]
		side = sum(math.hypot(c[(k + 1) % 4][0] - c[k][0], c[(k + 1) % 4][1] - c[k][1]) for k in range(4)) / 4
		# The image's step for one square along the board's columns (u) and rows (v), from the marker's corners
		u = ((x1 + x2 - x0 - x3) / (4 * h), (y1 + y2 - y0 - y3) / (4 * h))
		v = ((x2 + x3 - x0 - x1) / (4 * h), (y2 + y3 - y0 - y1) / (4 * h))
		frames.append(((x0 + x1 + x2 + x3) / 4, (y0 + y1 + y2 + y3) / 4, side, u, v))
	pairs = []
	for i in range(n):
		square = frames[i][2] / rho
		if not square > 0:
			continue
		for j in range(n):
			if j != i and ids[j] != ids[i] and \
					math.hypot(frames[j][0] - frames[i][0], frames[j][1] - frames[i][1]) <= o["neighbourRadius"] * square:
				pairs.append((i, j))
	scores = []
	for g in grids:
		squares = g["squares"]
		outside = sum(1 for k in ids if not 0 <= k < len(squares))
		agree = count = 0
		for i, j in pairs:
			if not (0 <= ids[i] < len(squares) and 0 <= ids[j] < len(squares)):
				continue
			du = squares[ids[j]][0] - squares[ids[i]][0]
			dv = squares[ids[j]][1] - squares[ids[i]][1]
			cx, cy, side, u, v = frames[i]
			px, py = cx + u[0] * du + v[0] * dv, cy + u[1] * du + v[1] * dv
			count += 1
			if math.hypot(px - frames[j][0], py - frames[j][1]) / side < o["agreeTol"]:
				agree += 1
		scores.append((agree, count, outside))
	return scores


def Identify(observations, squareMm=None, o=IDENTIFY):
	"""
	Which calib.io board DICT_5X5 markers come from. observations: one (ids,
	corners) per image (ScoreImage). Returns (status, presets, reason):
		"match": presets holds the one board;
		"size-ambiguous": calib.io sells the grid in several sizes, which an
			image can't tell apart, and squareMm picks none: presets holds them
			(their markers sit alike, so any of them finds the corners);
		"undecided": too few markers so far; "no-match": not a calib.io board.
	"""
	obs = [(list(map(int, ids)), corners) for ids, corners in observations if len(ids) >= o["minMarkers"]]
	if not obs:
		return "undecided", [], "no image with {}+ markers yet".format(o["minMarkers"])
	grids = Grids()
	totals = [[0, 0, 0, 0] for g in grids] # agree, pairs, ids past the end, ids
	allIds = set()
	for ids, corners in obs:
		allIds.update(ids)
		for t, (agree, pairs, outside) in zip(totals, ScoreImage(ids, corners, grids, o)):
			t[0] += agree
			t[1] += pairs
			t[2] += outside
			t[3] += len(ids)
	biggest = max(g["markers"] for g in grids)
	live = []
	for g, (agree, pairs, outside, seen) in zip(grids, totals):
		# Ruled out by two ids that a bigger calib.io grid has past this one's end, or by many of any kind:
		# one stray id (a misread marker) rules out nothing
		past = sum(1 for k in allIds if g["markers"] <= k < biggest)
		if past >= 2 or (outside >= 2 and outside > o["maxOutOfRange"] * seen):
			continue
		live.append((agree / pairs if pairs else 0.0, agree, pairs, g))
	seen = "{} markers in {} images, ids up to {}".format(sum(len(i) for i, c in obs), len(obs), max(allIds))
	if not live:
		return "no-match", [], "{}: ids past the last marker of every calib.io board".format(seen)
	if max(x[2] for x in live) < o["minPairs"]:
		return "undecided", [], "{}: too few neighbouring markers yet; show more of the board".format(seen)
	live.sort(key=lambda x: -x[0])
	best = live[0]
	if best[0] < o["fitFraction"]:
		return "no-match", [], "{}: they don't line up as any calib.io board (best {} x {}, {} of {} pairs)".format(
			seen, best[3]["rows"], best[3]["cols"], best[1], best[2])
	rival = next((x for x in live if x[3]["cols"] != best[3]["cols"]), None)
	if rival is not None and rival[0] > best[0] - o["margin"]:
		return "undecided", [], "{}: can't tell {} x {} from {} x {} yet".format(seen, best[3]["rows"], best[3]["cols"],
			rival[3]["rows"], rival[3]["cols"])
	# The same columns, fewer rows (15 x 24 and 17 x 24) agree on every id both have: the bigger stays in
	same = [x[3] for x in live if x[3]["cols"] == best[3]["cols"] and x[0] >= o["fitFraction"]]
	candidates = [p for g in same for p in g["presets"]]
	why = "{}: a {} x {} grid, {} of {} neighbouring pairs agree".format(seen, best[3]["rows"], best[3]["cols"],
		best[1], best[2])
	if len(candidates) == 1:
		return "match", candidates, why
	if squareMm is not None:
		picked = [p for p in candidates if abs(p["square_length"] - squareMm) < 1e-9]
		if len(picked) == 1:
			return "match", picked, why + "; the {} mm square picks the size".format(squareMm)
	return "size-ambiguous", candidates, why + "; calib.io sells it as {}: set calibrationSquareMm to say which"\
		.format(" or ".join("{} ({} mm squares)".format(p["sku"], p["square_length"]) for p in candidates))
