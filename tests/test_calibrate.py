"""calibrate: calibrat3 run after a calibration recording; which runner, its command, its report, the config."""

import json, os, sys

import pytest

from campy import calibrate, configurator
from campy.utils import boards


def Checkout(tmp_path, cli=True):
	root = tmp_path / "calibrat3"
	(root / "cli").mkdir(parents=True, exist_ok=True)
	(root / "index.html").write_text("<html></html>")
	if cli and not (root / "cli" / "calibrate.mjs").exists():
		(root / "cli" / "calibrate.mjs").write_text("// calibrat3's command line")
	return str(root)


def Settings(checkout, runner="auto", target=None):
	return calibrate.Settings({"calibrate": dict({"calibrat3": checkout, "runner": runner},
		**({"target": target} if target else {}))})


def Choose(settings, node=(22, 1), playwright=True, chrome=True):
	return calibrate.ChooseRunner(settings, which=lambda name: "/usr/bin/node" if node else None,
		nodeVersion=lambda path: node, playwright=lambda: playwright, chrome=lambda: "/chrome" if chrome else None)


# ------------------------------------------------------------------ settings and the runner

def test_settings():
	assert calibrate.Settings({}) is None and calibrate.Settings({"calibrate": None}) is None
	s = calibrate.Settings({"calibrate": {"calibrat3": "~/calibrat3"}})
	assert s == {"calibrat3": os.path.expanduser("~/calibrat3"), "runner": "auto", "target": None}
	for bad, words in [("x", "must be a dict"), ({"runner": "node"}, "calibrat3"),
			({"calibrat3": ".", "runner": "docker"}, "runner"), ({"calibrat3": ".", "target": 0}, "target"),
			({"calibrat3": ".", "out": "x"}, "unknown")]:
		with pytest.raises(ValueError, match=words):
			calibrate.Settings({"calibrate": bad})


def test_auto_takes_node_when_it_can_and_chrome_otherwise(tmp_path):
	checkout = Checkout(tmp_path)
	assert Choose(Settings(checkout)) == ("node", "/usr/bin/node", [])
	assert Choose(Settings(checkout), node=(18, 19))[0] == "chrome"
	assert Choose(Settings(checkout), node=None)[0] == "chrome"
	assert Choose(Settings(Checkout(tmp_path / "old", cli=False)))[0] == "chrome" # a checkout without the command line
	runner, node, problems = Choose(Settings(checkout), node=(18, 19), playwright=False)
	assert runner is None and "too old" in problems[0] and "pip install playwright" in problems[1]


def test_a_runner_can_be_forced(tmp_path):
	checkout = Checkout(tmp_path)
	assert Choose(Settings(checkout, "chrome"))[0] == "chrome"
	runner, _, problems = Choose(Settings(checkout, "chrome"), chrome=False)
	assert runner is None and problems == ["Google Chrome is not installed"]
	runner, _, problems = Choose(Settings(checkout, "node"), node=None)
	assert runner is None and "not on PATH" in problems[0]


def test_no_checkout_says_how_to_get_one(tmp_path):
	runner, _, problems = Choose(Settings(str(tmp_path / "nowhere")))
	assert runner is None and "git clone https://github.com/talmolab/calibrat3" in problems[0]


def test_the_real_node_version_is_read():
	node = calibrate.shutil.which("node")
	if node is None:
		pytest.skip("no node here")
	assert calibrate.NodeVersion(node) >= (1, 0)


# ------------------------------------------------------------------ the command line

def test_the_node_command(tmp_path):
	run = str(tmp_path / "run")
	board = boards.Board("CCT300200C")
	command = calibrate.NodeCommand("node", "/c3", run, board, 300, help="--board-x N\n")
	assert command == ["node", os.path.join("/c3", "cli", "calibrate.mjs"), run, "--out",
		os.path.join(run, "calibration.toml"), "--report", os.path.join(run, "fit_report.json"), "--target", "300"]
	# A command line that takes --board is given the preset too
	help = "  --board B   preset id, SKU or auto\n  --square L\n"
	assert calibrate.NodeCommand("node", "/c3", run, board, None, help)[-2:] == ["--board", "calibio-300x200-coarse"]
	assert calibrate.NodeCommand("node", "/c3", run, boards.Board("auto", 20), None, help)[-4:] == \
		["--board", "auto", "--square", "20"]
	# A custom board is only in board.toml
	custom = boards.Board({"board_x": 8, "board_y": 11, "square_length": 24, "marker_length": 18.75, "marker_bits": 4,
		"dict_size": 1000})
	assert "--board" not in calibrate.NodeCommand("node", "/c3", run, custom, None, help)
	with pytest.raises(calibrate.CalibrateError, match="can't identify the board"):
		calibrate.NodeCommand("node", "/c3", run, boards.Board("auto"), None, "--board-x N")


# ------------------------------------------------------------------ the report

TOML = """[cam_0]
name = "back"
size = [1280, 1024]

[cam_1]
name = "mid"

[metadata]
name = "not a camera"
"""

REPORT = {
	"generator": "calibrat3-cli",
	"detection": {"frames": 100, "perView": [88, 92, 0]},
	"intrinsics": [{"name": "back", "rms": 0.4}, {"name": "mid", "rms": 0.5}, {"name": "side", "error": True}],
	"final": {"refinedBySba": True,
		"reprojection": {"overall": {"median": 0.31}, "perView": [{"median": 0.28, "p95": 0.7}, {"median": 0.35,
			"p95": 0.9}, None]},
		"cameras": [{"name": "back", "center": [0, 0, 0]}, {"name": "mid"}, {"name": "side", "error": "not calibrated"}]},
	}


def test_the_camera_names_of_a_calibration():
	assert calibrate.CalibrationNames(TOML) == ["back", "mid"]
	assert calibrate.CalibrationNames('[cam_10]\nname = "b"\n[cam_2]\nname = "a"\n') == ["a", "b"]


def test_the_report_says_each_cameras_error_and_whether_it_is_in_the_calibration():
	rows = calibrate.ReadReport(REPORT, TOML)
	assert rows == [
		{"name": "back", "median_px": 0.28, "p95_px": 0.7, "board_frames": 88, "in_calibration": True, "why": None},
		{"name": "mid", "median_px": 0.35, "p95_px": 0.9, "board_frames": 92, "in_calibration": True, "why": None},
		{"name": "side", "median_px": None, "p95_px": None, "board_frames": 0, "in_calibration": False,
			"why": "not calibrated"},
		]
	lines = calibrate.Describe(rows, "/run/calibration.toml", 0.31)
	assert lines[0] == "Calibration: 2 of 3 cameras in /run/calibration.toml (median reprojection error 0.31 px)"
	assert lines[1] == "  back  median 0.28 px, p95 0.70 px, board in 88 sampled frames: in calibration.toml"
	assert lines[3] == "  side  no reprojection error, board in 0 sampled frames: NOT in calibration.toml (not calibrated)"


def test_the_command_lines_newer_report():
	report = {"ok": True, "error": None, "cameras": [
		{"name": "back", "inCalibration": True, "reason": None, "framesSampled": 100, "framesWithBoard": 88,
			"reprojectionPx": {"median": 0.28, "p95": 0.7, "mean": 0.3}, "intrinsicsRmsPx": 0.4},
		{"name": "mid", "inCalibration": True, "framesWithBoard": 92, "reprojectionPx": {"median": 0.35, "p95": 0.9}},
		{"name": "side", "inCalibration": False, "reason": "no intrinsics (too few frames with the board)",
			"framesWithBoard": 0, "reprojectionPx": None}]}
	rows = calibrate.ReadReport(report, TOML)
	assert rows == calibrate.ReadReport(REPORT, TOML)[:2] + [{"name": "side", "median_px": None, "p95_px": None,
		"board_frames": 0, "in_calibration": False, "why": "no intrinsics (too few frames with the board)"}]


def test_a_report_of_another_shape_still_gives_the_cameras_in_the_calibration():
	assert calibrate.ReadReport({}, TOML) == [
		{"name": n, "median_px": None, "p95_px": None, "board_frames": None, "in_calibration": True, "why": None}
		for n in ("back", "mid")]
	odd = {"final": {"cameras": [{"name": "back"}, "?"], "reprojection": {"perView": "?"}}, "detection": []}
	rows = calibrate.ReadReport(odd, TOML)
	assert rows[0]["name"] == "back" and rows[0]["in_calibration"] and rows[1]["name"] is None
	assert calibrate.ReadReport({"intrinsics": [{"error": True}], "final": {"cameras": [{"name": "x"}]}})[0]["why"] == \
		"no intrinsics"


# ------------------------------------------------------------------ after the recording

def Params(tmp_path, **kw):
	params = {"numCams": 2, "cameraNames": ["back", "mid"], "videoFilename": "calibration.mp4", "sessionFolder": True,
		"videoFolder": str(tmp_path), "calibrationBoard": "CCT300200C", "calibrationSquareMm": None,
		"calibrate": {"calibrat3": Checkout(tmp_path)}}
	params.update(kw)
	return params


def Run(tmp_path, cams=("back", "mid")):
	run = tmp_path / "2026-11-24_14-05-11"
	for c in cams:
		(run / c / "calibration_images").mkdir(parents=True)
		(run / c / "calibration_images" / "calibration.mp4").write_bytes(b"")
		(run / c / "metadata.csv").write_text("")
	return str(run)


def test_after_a_calibration_recording_campy_writes_the_board_and_reads_the_result(tmp_path, monkeypatch):
	params, run = Params(tmp_path), Run(tmp_path)
	calls = []

	def FakeNode(node, checkout, folder, board, target, say):
		calls.append((node, folder, board))
		with open(os.path.join(folder, "calibration.toml"), "w") as f:
			f.write(TOML)
		with open(os.path.join(folder, "fit_report.json"), "w") as f:
			json.dump(dict(REPORT, final=dict(REPORT["final"], cameras=REPORT["final"]["cameras"][:2])), f)
	monkeypatch.setattr(calibrate, "RunNode", FakeNode)
	said = []
	rows = calibrate.AfterRecording(params, run, say=said.append, choose=lambda s: ("node", "node", []))
	assert [r["name"] for r in rows] == ["back", "mid"] and all(r["in_calibration"] for r in rows)
	assert calls == [("node", run, boards.Board("CCT300200C"))]
	with open(os.path.join(run, "board.toml")) as f:
		assert f.read() == boards.BoardToml(boards.Board("CCT300200C"))
	assert any(s.startswith("Calibration: 2 of 2 cameras in " + os.path.join(run, "calibration.toml")) for s in said)
	# LUC3D takes any other root file with "calib" in its name for a second calibration
	assert [n for n in os.listdir(run) if "calib" in n.lower()] == ["calibration.toml"]


def test_a_failure_says_why_and_leaves_the_recording(tmp_path, monkeypatch):
	params, run = Params(tmp_path), Run(tmp_path)

	def Fails(*args):
		raise calibrate.CalibrateError("calibrat3's command line stopped with exit code 1: no board found")
	monkeypatch.setattr(calibrate, "RunNode", Fails)
	said = []
	assert calibrate.AfterRecording(params, run, say=said.append, choose=lambda s: ("node", "node", [])) is None
	assert said[-1] == "Could not calibrate the cameras: calibrat3's command line stopped with exit code 1: no board " \
		"found. The recording is intact in {}.".format(run)
	assert os.path.isfile(os.path.join(run, "back", "calibration_images", "calibration.mp4"))
	assert not os.path.exists(os.path.join(run, "calibration.toml"))


def test_nothing_to_run_and_missing_videos_say_why(tmp_path):
	run = Run(tmp_path, cams=("back",))
	said = []
	calibrate.AfterRecording(Params(tmp_path), run, say=said.append, choose=lambda s: (None, None, ["no Node"]))
	assert "can't run here: no Node" in said[-1]
	calibrate.AfterRecording(Params(tmp_path), run, say=said.append, choose=lambda s: ("node", "node", []))
	assert "no calibration video for mid" in said[-1]
	calibrate.AfterRecording(Params(tmp_path, sessionFolder=False), run, say=said.append)
	assert "sessionFolder is not True" in said[-1]


def test_auto_uses_the_board_the_calibration_view_identified(tmp_path):
	params = Params(tmp_path, calibrationBoard="auto")
	found = {"status": "match", "board": boards.Board("CCT300200C"), "reason": "a 9 x 14 grid"}
	assert calibrate.RunBoard(params, found)[0] == boards.Board("CCT300200C")
	assert calibrate.RunBoard(params, None)[0] == {"preset": "auto"}
	assert calibrate.RunBoard(Params(tmp_path, calibrationBoard=None), None)[0] == {"preset": "auto"}
	with pytest.raises(calibrate.CalibrateError, match="calibrationSquareMm"):
		calibrate.RunBoard(params, {"status": "size-ambiguous", "candidates": ["calibio-600x400-coarse",
			"calibio-300x200-coarse"]})
	# A named board is never replaced
	assert calibrate.RunBoard(Params(tmp_path, calibrationBoard="CCT600400F"), found)[0]["preset"] == \
		"calibio-600x400-fine"


def test_only_calibration_recordings_are_calibrated_and_checked_before_recording(tmp_path):
	assert not calibrate.Wanted(Params(tmp_path, videoFilename="0.mp4"))
	assert not calibrate.Wanted(Params(tmp_path, calibrate=None))
	assert calibrate.Wanted(Params(tmp_path))
	assert calibrate.Check(Params(tmp_path, videoFilename="0.mp4")) == []
	problems = calibrate.Check(Params(tmp_path, sessionFolder=False, calibrate={"calibrat3": str(tmp_path / "x")}))
	assert "sessionFolder" in problems[0] and "no calibrat3 checkout" in problems[1]


# ------------------------------------------------------------------ the config

def Parse(monkeypatch, tmp_path, text, *args):
	path = tmp_path / "config.yaml"
	path.write_text(text)
	monkeypatch.setattr(sys, "argv", ["campy-acquire", str(path)] + list(args))
	monkeypatch.setattr(os, "environ", dict(os.environ)) # ConfigureParams sets IMAGEIO_FFMPEG_EXE
	return configurator.ConfigureParams()


def test_an_existing_config_is_unchanged(monkeypatch, tmp_path):
	params = Parse(monkeypatch, tmp_path, 'videoFolder: "./test"\nnumCams: 2\n')
	assert (params["calibrationMode"], params["calibrationBoard"], params["calibrationSquareMm"], params["calibrate"],
		params["displayMode"]) == (False, None, None, None, "per-camera")


def test_calibration_keys_from_the_config_and_the_command_line(monkeypatch, tmp_path):
	params = Parse(monkeypatch, tmp_path, 'numCams: 2\ncalibrationMode: True\ncalibrationBoard: CCT300200C\n'
		'calibrate:\n  calibrat3: ../calibrat3\n  runner: node\n')
	assert params["displayMode"] == "one-window" # the view is drawn in the one window
	assert params["calibrationBoard"] == "CCT300200C" and params["calibrate"]["runner"] == "node"
	params = Parse(monkeypatch, tmp_path, "numCams: 2\n", "--calibrationBoard", "auto", "--calibrationSquareMm", "20",
		"--calibrate", "{calibrat3: ../c3}")
	assert params["calibrationBoard"] == "auto" and params["calibrationSquareMm"] == 20.0
	assert params["calibrate"] == {"calibrat3": "../c3"}
	params = Parse(monkeypatch, tmp_path, "numCams: 1\ncalibrationBoard: {board_x: 8, board_y: 11, square_length: 24, "
		"marker_length: 18.75, marker_bits: 4, dict_size: 1000}\n")
	assert boards.Board(params["calibrationBoard"])["board_x"] == 8


@pytest.mark.parametrize("text,words", [
	("calibrationBoard: CCT1\n", "no calib.io board"),
	("calibrationMode: yes please\n", "calibrationMode"),
	("calibrationSquareMm: -3\n", "calibrationSquareMm"),
	("calibrate: {runner: node}\n", "calibrat3"),
])
def test_a_wrong_calibration_key_stops_before_recording(monkeypatch, tmp_path, text, words):
	with pytest.raises(ValueError, match=words):
		Parse(monkeypatch, tmp_path, "numCams: 1\n" + text)


FAKE_CLI = r'''
# A stand-in for calibrat3's cli/calibrate.mjs, run by Python in place of node
import json, sys
args = sys.argv[1:]
if args == ["--help"]:
	print("  --board B   a calib.io board, or auto\n  --square L\n")
	sys.exit(0)
out = args[args.index("--out") + 1]
report = args[args.index("--report") + 1]
print("[  0.1s] " + " ".join(args[3:]))
if "--square" not in args:
	json.dump({"ok": False, "exitCode": 3, "error": "Auto (calib.io): the board is a 9 x 14 calib.io grid, sold in two "
		"sizes; give its square size with --square."}, open(report, "w"))
	sys.exit(3)
open(out, "w").write('[cam_0]\nname = "back"\n\n[cam_1]\nname = "mid"\n')
json.dump({"ok": True, "board": {"label": "calib.io 300 x 200 mm coarse", "method": "auto"}, "cameras": [
	{"name": "back", "inCalibration": True, "framesWithBoard": 90, "reprojectionPx": {"median": 0.2, "p95": 0.5}},
	{"name": "mid", "inCalibration": True, "framesWithBoard": 80, "reprojectionPx": {"median": 0.3, "p95": 0.6}}]},
	open(report, "w"))
'''


def test_the_command_line_runs_and_an_unsettled_board_says_what_to_set(tmp_path):
	checkout = Checkout(tmp_path)
	with open(os.path.join(checkout, "cli", "calibrate.mjs"), "w") as f:
		f.write(FAKE_CLI)
	node = lambda s: ("node", sys.executable, [])
	run, said = Run(tmp_path), []
	params = Params(tmp_path, calibrationBoard="auto", calibrate={"calibrat3": checkout, "target": 50})
	assert calibrate.AfterRecording(params, run, say=said.append, choose=node) is None
	assert "exit code 3: Auto (calib.io)" in said[-1] and "calibrationSquareMm" in said[-1]
	assert any("calibrat3: [  0.1s] --report" in s and "--board auto --target 50" in s for s in said)
	rows = calibrate.AfterRecording(dict(params, calibrationSquareMm=20), run, say=said.append, choose=node)
	assert [(r["name"], r["median_px"], r["in_calibration"]) for r in rows] == [("back", 0.2, True), ("mid", 0.3, True)]
	assert "calibrat3's board: calib.io 300 x 200 mm coarse (identified from its markers)" in said
	with open(os.path.join(run, "fit_log.txt")) as f:
		assert "--board auto --square 20 --target 50" in f.read()
