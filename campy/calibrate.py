"""
Calibrating the cameras after a calibration recording (config calibrate).

A calibration recording is one whose videoFilename has "calibration" in it,
recorded with sessionFolder: True, so each camera's video is in
<run>/<camera>/calibration_images/ (utils/folders.py). With

	calibrate:
	  calibrat3: /path/to/calibrat3 # a checkout of talmolab/calibrat3
	  runner: auto # or "node" or "chrome"
	  target: 300 # frames sampled for the board (optional)

campy then writes <run>/board.toml (calibrationBoard, utils/boards.py) and
has calibrat3 calibrate the run, which writes <run>/calibration.toml
(anipose's format, one [cam_N] per camera, named as cameraNames), the file
LUC3D and sleap-anipose look for in a session folder. It also writes
<run>/fit_report.json (each camera's reprojection error, and more) and
<run>/fit_log.txt (what calibrat3 did): no other file at the run's root has
"calib" in its name, which LUC3D would take for a second calibration.

calibrat3 runs either:
	- "node": its command line, cli/calibrate.mjs, under Node.js 20 or newer
	  (ffmpeg decodes the videos); or
	- "chrome": its page, in this computer's Google Chrome, headless, driven
	  by Playwright's Python package (pip install playwright; it uses the
	  installed Chrome, no browser download).
"auto" (the default) takes Node when it can, else Chrome.

A failure says why, and leaves the recording as it is.
"""

import importlib.util, json, os, re, shutil, subprocess, sys, time

from campy.utils import boards, folders

RUNNERS = ("auto", "node", "chrome")
NODE_MIN = (20, 0)
CLI = os.path.join("cli", "calibrate.mjs")
CALIBRATION = "calibration.toml"
BOARD = "board.toml"
REPORT = "fit_report.json"
LOG = "fit_log.txt"


class CalibrateError(Exception):
	pass


def Settings(params):
	"""params' calibrate as {calibrat3, runner, target}, or None. Raises ValueError, saying why."""
	spec = params.get("calibrate")
	if spec is None:
		return None
	if not isinstance(spec, dict) or "calibrat3" not in spec:
		raise ValueError("calibrate must be a dict with calibrat3: <a calibrat3 checkout> (and optionally runner: "
			"auto, node or chrome, and target: <frames>), not {!r}".format(spec))
	unknown = sorted(set(spec) - {"calibrat3", "runner", "target"})
	if unknown:
		raise ValueError("calibrate: unknown key{} {} (known: calibrat3, runner, target)".format(
			"s" if len(unknown) > 1 else "", ", ".join(unknown)))
	runner = str(spec.get("runner", "auto")).lower()
	if runner not in RUNNERS:
		raise ValueError("calibrate: runner must be one of {}, not {!r}".format(", ".join(RUNNERS), spec["runner"]))
	target = spec.get("target")
	if target is not None and (isinstance(target, bool) or not isinstance(target, int) or target < 1):
		raise ValueError("calibrate: target must be a whole number of frames, not {!r}".format(target))
	return {"calibrat3": os.path.abspath(os.path.expanduser(str(spec["calibrat3"]))), "runner": runner, "target": target}


def Wanted(params):
	"""Whether this run is a calibration recording that campy is to calibrate."""
	return params.get("calibrate") is not None and folders.IsCalibrationVideo(params)


# ------------------------------------------------------------------ which runner

def NodeVersion(node):
	"""node's version as a tuple, or None."""
	try:
		out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=20).stdout
	except (OSError, subprocess.SubprocessError):
		return None
	m = re.match(r"v?(\d+)\.(\d+)", out.strip())
	return (int(m.group(1)), int(m.group(2))) if m else None


# Where Playwright's "chrome" channel finds Google Chrome
CHROME = {
	"win32": [os.path.join(os.environ.get(v, ""), "Google", "Chrome", "Application", "chrome.exe")
		for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")],
	"darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
	"linux": ["/opt/google/chrome/chrome"],
	}


def ChromeFound():
	for path in CHROME.get(sys.platform, CHROME["linux"]):
		if path and os.path.isfile(path):
			return path
	return None


def PlaywrightFound():
	return importlib.util.find_spec("playwright") is not None


def ChooseRunner(settings, which=shutil.which, nodeVersion=NodeVersion, playwright=PlaywrightFound,
		chrome=ChromeFound):
	"""
	(runner, node, problems): "node" or "chrome", the node binary for "node",
	and why the runner asked for (or, for "auto", either) can't run. runner
	is None when none can.
	"""
	checkout = settings["calibrat3"]
	problems = []
	nodeProblems, chromeProblems = [], []
	if not os.path.isfile(os.path.join(checkout, "index.html")):
		problems.append("no calibrat3 checkout at {} (git clone https://github.com/talmolab/calibrat3, and give its "
			"folder as calibrate: calibrat3:)".format(checkout))
		return None, None, problems
	node = which("node")
	if not os.path.isfile(os.path.join(checkout, CLI)):
		nodeProblems.append("this calibrat3 checkout has no command line ({})".format(CLI))
	if node is None:
		nodeProblems.append("Node.js is not installed (node is not on PATH)")
	else:
		version = nodeVersion(node)
		if version is None or version < NODE_MIN:
			nodeProblems.append("Node.js {} is too old: calibrat3's command line needs {} or newer".format(
				"v{}.{}".format(*version) if version else "(version unknown)", NODE_MIN[0]))
	if not playwright():
		chromeProblems.append("Playwright's Python package is not in this environment ({}): pip install playwright"
			.format(sys.executable))
	if chrome() is None:
		chromeProblems.append("Google Chrome is not installed")
	wanted = settings["runner"]
	if wanted in ("auto", "node") and not nodeProblems:
		return "node", node, []
	if wanted in ("auto", "chrome") and not chromeProblems:
		return "chrome", None, []
	if wanted == "node":
		return None, None, nodeProblems
	if wanted == "chrome":
		return None, None, chromeProblems
	return None, None, ["Node: " + "; ".join(nodeProblems), "Chrome: " + "; ".join(chromeProblems)]


def Check(params):
	"""
	Before a calibration recording: what would keep campy from calibrating
	it afterwards ([text], empty when nothing), so that it isn't recorded only
	to find out then.
	"""
	if not Wanted(params):
		return []
	problems = []
	if not folders.SessionFolders(params):
		problems.append("sessionFolder is not True, so the cameras' videos are not laid out for calibrat3 "
			"(<camera>/calibration_images/)")
	try:
		runner, _, why = ChooseRunner(Settings(params))
		problems += why
	except ValueError as e:
		problems.append(str(e))
	return problems


# ------------------------------------------------------------------ the board

def RunBoard(params, found=None):
	"""
	The board to calibrate with (boards.Board): calibrationBoard, or for
	"auto" (or none given) the calib.io board the calibration view identified
	(found: calibview's Result), if it did. Raises CalibrateError when the
	board is known to be unclear.
	"""
	board = boards.Board(params.get("calibrationBoard"), params.get("calibrationSquareMm")) or \
		boards.Board(boards.AUTO, params.get("calibrationSquareMm"))
	if board["preset"] != boards.AUTO:
		return board, None
	found = found or {}
	if found.get("status") == "match" and found.get("board"):
		return found["board"], "identified in the calibration view: " + found.get("reason", "")
	if found.get("status") == "size-ambiguous":
		raise CalibrateError("the calibration view found the board's grid, but calib.io sells it in several sizes "
			"({}): set calibrationSquareMm, or name the board in calibrationBoard".format(
				", ".join(found.get("candidates", []))))
	return board, None


# ------------------------------------------------------------------ the report

def CalibrationNames(text):
	"""The camera names in a calibration.toml: [cam_N] sections' name, in order of N."""
	names, section = {}, None
	for line in text.splitlines():
		line = line.strip()
		m = re.match(r"^\[(.+)\]$", line)
		if m:
			section = m.group(1).strip()
			continue
		m = re.match(r'^name\s*=\s*"(.*)"\s*$', line)
		if m and section and re.match(r"^cam_\d+$", section):
			names[int(section[4:])] = m.group(1)
	return [names[k] for k in sorted(names)]


def ReadReport(report, calibrationText=""):
	"""
	Each camera's result, from calibrat3's report (its command line's
	--report JSON; the Chrome runner writes the same keys): [{name,
	median_px, p95_px, board_frames, in_calibration, why}]. Whether a camera
	is in the calibration comes from calibrationText (calibration.toml)
	itself. The report's format is young, so it is read defensively, and a
	value it lacks is None. Two shapes are read: a top-level "cameras" list
	({name, reason, framesWithBoard, reprojectionPx: {median, p95}}), and
	the first command line's final.cameras[i] ({name, error}) beside
	final.reprojection.perView[i] ({median, p95}), detection.perView[i] and
	intrinsics[i].error.
	"""
	def get(obj, *keys):
		for k in keys:
			if isinstance(obj, dict):
				obj = obj.get(k)
			elif isinstance(obj, list) and isinstance(k, int):
				obj = obj[k] if 0 <= k < len(obj) else None
			else:
				return None
		return obj

	def number(v):
		return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

	report = report if isinstance(report, dict) else {}
	written = CalibrationNames(calibrationText or "")
	rows = []
	cameras = report.get("cameras")
	if isinstance(cameras, list) and all(isinstance(c, dict) for c in cameras):
		for cam in cameras:
			rows.append({"name": cam.get("name"), "median_px": number(get(cam, "reprojectionPx", "median")),
				"p95_px": number(get(cam, "reprojectionPx", "p95")), "board_frames": number(cam.get("framesWithBoard")),
				"why": cam.get("reason")})
	else:
		cameras = get(report, "final", "cameras")
		if not isinstance(cameras, list):
			cameras = [{"name": v.get("name")} for v in (get(report, "session", "views") or []) if isinstance(v, dict)]
		for i, cam in enumerate(cameras):
			cam = cam if isinstance(cam, dict) else {}
			rows.append({"name": cam.get("name"),
				"median_px": number(get(report, "final", "reprojection", "perView", i, "median")),
				"p95_px": number(get(report, "final", "reprojection", "perView", i, "p95")),
				"board_frames": number(get(report, "detection", "perView", i)),
				"why": cam.get("error") or ("no intrinsics" if get(report, "intrinsics", i, "error") else None)})
	for row in rows:
		row["in_calibration"] = row["name"] in written
		row["why"] = None if row["in_calibration"] or not row["why"] else str(row["why"])
	rows += [{"name": n, "median_px": None, "p95_px": None, "board_frames": None, "why": None, "in_calibration": True}
		for n in written if n not in {r["name"] for r in rows}]
	return [{k: r[k] for k in ("name", "median_px", "p95_px", "board_frames", "in_calibration", "why")} for r in rows]


def Describe(rows, path, overall=None):
	"""What to print: one line for the file, one per camera."""
	inside = [r for r in rows if r["in_calibration"]]
	lines = ["Calibration: {} of {} cameras in {}{}".format(len(inside), len(rows), path,
		" (median reprojection error {:.2f} px)".format(overall) if overall is not None else "")]
	width = max([len(str(r["name"])) for r in rows] + [4])
	for r in rows:
		error = "median {:.2f} px, p95 {:.2f} px".format(r["median_px"], r["p95_px"] if r["p95_px"] is not None
			else float("nan")) if r["median_px"] is not None else "no reprojection error"
		frames = ", board in {:,} sampled frames".format(int(r["board_frames"])) if r["board_frames"] is not None else ""
		where = "in calibration.toml" if r["in_calibration"] else "NOT in calibration.toml" + (
			" ({})".format(r["why"]) if r["why"] else "")
		lines.append("  {:<{}}  {}{}: {}".format(str(r["name"]), width, error, frames, where))
	return lines


# ------------------------------------------------------------------ the runners

def NodeHelp(node, checkout):
	try:
		return subprocess.run([node, os.path.join(checkout, CLI), "--help"], capture_output=True, text=True,
			timeout=60).stdout
	except (OSError, subprocess.SubprocessError):
		return ""


def NodeCommand(node, checkout, folder, board, target=None, help=""):
	"""
	calibrat3's command line for folder. The board goes in board.toml; a
	command line that takes --board (calibrat3's --board <id|SKU|auto>) is
	also given the preset, or "auto" and the square size.
	"""
	command = [node, os.path.join(checkout, CLI), folder, "--out", os.path.join(folder, CALIBRATION),
		"--report", os.path.join(folder, REPORT)]
	if board.get("preset") and re.search(r"--board[ =]", help or ""):
		command += ["--board", board["preset"]]
		if board["preset"] == boards.AUTO and "square_length" in board and "--square" in help:
			command += ["--square", str(board["square_length"])]
	elif board.get("preset") == boards.AUTO:
		raise CalibrateError("this calibrat3 checkout's command line can't identify the board (it has no --board "
			"auto): name the board in calibrationBoard, or use runner: chrome")
	if target:
		command += ["--target", str(int(target))]
	return command


def RunNode(node, checkout, folder, board, target=None, say=print):
	command = NodeCommand(node, checkout, folder, board, target, NodeHelp(node, checkout))
	say("Calibrating with calibrat3's command line: " + " ".join(command))
	with open(os.path.join(folder, LOG), "w", encoding="utf-8") as log:
		process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
			encoding="utf-8", errors="replace", cwd=checkout)
		tail = []
		for line in process.stdout:
			log.write(line)
			line = line.rstrip()
			tail = (tail + [line])[-5:]
			say("  calibrat3: " + line)
		code = process.wait()
	if code != 0:
		why = None
		try:
			with open(os.path.join(folder, REPORT), encoding="utf-8") as f:
				why = json.load(f).get("error")
		except (OSError, ValueError, AttributeError):
			pass
		why = why or (tail[-1] if tail else "no output")
		if code == 3: # the board isn't settled (an "auto" board's size, or not a calib.io board)
			why += " (in campy's config: calibrationSquareMm, or name the board in calibrationBoard)"
		raise CalibrateError("calibrat3's command line stopped with exit code {}: {}".format(code, why))


def RunChrome(checkout, folder, board, target=None, say=print, timeout_s=3600):
	"""calibrat3's page in the installed Chrome, headless (Playwright), as a person would use it."""
	import functools, threading
	from http.server import ThreadingHTTPServer
	try:
		from playwright.sync_api import sync_playwright
	except ImportError:
		raise CalibrateError("Playwright's Python package is not in this environment: pip install playwright")
	# calibrat3's own server (Range requests, which its video reader needs)
	spec = importlib.util.spec_from_file_location("calibrat3_server", os.path.join(checkout, "server.py"))
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	class Quiet(module.Handler):
		def log_message(self, *args):
			pass

	server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=checkout))
	server.daemon_threads = True
	threading.Thread(target=server.serve_forever, daemon=True).start()
	query = ""
	if board.get("preset"):
		query = "?board=" + board["preset"]
		if board["preset"] == boards.AUTO and "square_length" in board:
			query += "&square={}".format(board["square_length"])
	url = "http://127.0.0.1:{}/index.html{}".format(server.server_address[1], query)
	say("Calibrating with calibrat3's page in Chrome (headless): " + url)
	t0 = time.monotonic()
	try:
		with sync_playwright() as p:
			try:
				browser = p.chromium.launch(channel="chrome", headless=True)
			except Exception as e:
				raise CalibrateError("could not start Chrome: {}".format(str(e).splitlines()[0]))
			try:
				page = browser.new_page(viewport={"width": 1600, "height": 1000})

				def wait(predicate, what):
					# Until predicate holds on the page; calibrat3's error banner ends it
					deadline = time.monotonic() + timeout_s
					while time.monotonic() < deadline:
						banner = page.evaluate("() => { const e = document.getElementById('errorMsg'); "
							"return e && e.style.display === 'block' ? e.textContent : null; }")
						if banner:
							raise CalibrateError("calibrat3, {}: {}".format(what, banner.strip()))
						if page.evaluate(predicate):
							say("  calibrat3: {} done ({:.0f} s)".format(what, time.monotonic() - t0))
							return
						time.sleep(0.5)
					raise CalibrateError("calibrat3, {}: not done after {:.0f} min".format(what, timeout_s / 60))

				state = "window.__calibrat3.state"
				page.goto(url, wait_until="load")
				wait("() => document.getElementById('workerStatus').classList.contains('ok')", "starting")
				page.set_input_files("#folderInput", folder)
				wait("() => {0}.views.length >= 2 && {0}.totalFrames > 0".format(state), "opening the videos")
				names = page.evaluate("() => {}.views.map(v => v.name)".format(state))
				if target:
					page.fill("#targetSamples", str(int(target)))
					page.dispatch_event("#targetSamples", "input")
				page.evaluate("() => {{ window.__campyBefore = {}.detections; }}".format(state))
				page.click("#runDetectionBtn")
				wait("() => !{0}.detectionRunning && {0}.detections && {0}.detections !== window.__campyBefore"
					.format(state), "finding the board")
				found = page.evaluate("() => {}.detections.summary(6)".format(state))
				page.click("#computeIntrinsicsBtn")
				wait("() => !document.getElementById('computeIntrinsicsBtn').disabled && {}.intrinsics.length > 0"
					.format(state), "intrinsics")
				intrinsics = page.evaluate("() => {}.intrinsics.map(r => r ? {{rms: r.rmsError}} : {{error: true}})"
					.format(state))
				page.click("#computeExtrinsicsBtn")
				wait("() => {}.reproj !== null".format(state), "the cameras' positions")
				page.wait_for_selector("#runSbaBtn:not([disabled])", timeout=60000)
				page.click("#runSbaBtn")
				wait("() => {}.sbaResult !== null && !document.getElementById('runSbaBtn').disabled".format(state),
					"the bundle adjustment")
				reproj = page.evaluate("() => {}.reproj.summary".format(state))
				errors = page.evaluate("() => {}.extrinsics.map(e => !e ? 'not calibrated' : e.error || null)".format(state))
				toml = page.evaluate("async () => (await import('./ui/stage-export.js')).buildToml()")
				log = page.evaluate("() => Array.from(document.querySelectorAll('#logBody .log-entry'))"
					".map(x => x.textContent)")
			finally:
				browser.close()
	finally:
		server.shutdown()
		server.server_close()
	with open(os.path.join(folder, LOG), "w", encoding="utf-8") as f:
		f.write("\n".join(log) + "\n")
	# The command line's report keys (ReadReport)
	report = {"generator": "campy, calibrat3's page in Chrome", "detection": found, "intrinsics": intrinsics,
		"final": {"reprojection": reproj, "cameras": [dict({"name": n}, **({"error": e} if e else {}))
			for n, e in zip(names, errors)]}}
	with open(os.path.join(folder, REPORT), "w", encoding="utf-8") as f:
		json.dump(report, f, indent=1)
	if not toml:
		raise CalibrateError("calibrat3 calibrated no camera")
	with open(os.path.join(folder, CALIBRATION), "w", encoding="utf-8") as f:
		f.write(toml)


# ------------------------------------------------------------------ after the recording

def AfterRecording(params, folder, found=None, say=print, choose=ChooseRunner):
	"""
	Calibrates the calibration recording in folder (the module's doc). found:
	what the calibration view found (calibview's Result), or None. Returns
	each camera's result (ReadReport), or None when it could not calibrate;
	never raises.
	"""
	try:
		if not folders.SessionFolders(params):
			raise CalibrateError("sessionFolder is not True: calibrat3 needs each camera's video in "
				"<camera>/calibration_images/")
		settings = Settings(params)
		runner, node, problems = choose(settings)
		if runner is None:
			raise CalibrateError("calibrat3 can't run here: " + "; ".join(problems))
		names = [str(n) for n in params["cameraNames"][:params["numCams"]]]
		missing = [n for n in names if not os.path.isdir(os.path.join(folder, n, folders.CALIBRATION_FOLDER))]
		if missing:
			raise CalibrateError("no calibration video for {}".format(", ".join(missing)))
		board, how = RunBoard(params, found)
		with open(os.path.join(folder, BOARD), "w", encoding="utf-8") as f:
			f.write(boards.BoardToml(board))
		say("Board: {}{}".format(boards.Describe(board), " ({})".format(how) if how else ""))
		t0 = time.monotonic()
		if runner == "node":
			RunNode(node, settings["calibrat3"], folder, board, settings["target"], say)
		else:
			RunChrome(settings["calibrat3"], folder, board, settings["target"], say)
		path = os.path.join(folder, CALIBRATION)
		if not os.path.isfile(path):
			raise CalibrateError("calibrat3 wrote no calibration.toml")
		with open(path, encoding="utf-8") as f:
			text = f.read()
		try:
			with open(os.path.join(folder, REPORT), encoding="utf-8") as f:
				report = json.load(f)
		except (OSError, ValueError):
			report = {}
		rows = ReadReport(report, text)
		used = report.get("board") if isinstance(report.get("board"), dict) else {}
		if used.get("label") or used.get("method") == "auto":
			say("calibrat3's board: {}{}".format(used.get("label") or "?", " (identified from its markers)"
				if used.get("method") == "auto" else ""))
		overall = (((report.get("final") or {}).get("reprojection") or {}).get("overall") or {}).get("median")
		for line in Describe(rows, path, overall if isinstance(overall, (int, float)) else None):
			say(line)
		say("Took {:.0f} s; report in {}. To see a session in 3D, copy calibration.toml into its folder, beside "
			"its camera folders, and open it in LUC3D (Load Session Folder) or sleap-anipose.".format(
			time.monotonic() - t0, os.path.join(folder, REPORT)))
		return rows
	except (CalibrateError, ValueError, OSError) as e:
		say("Could not calibrate the cameras: {}. The recording is intact in {}.".format(e, folder))
		return None
