"""
One status line at the bottom of the console while campy records, rewritten in
place about once a second (statusLine), instead of every camera's
"CameraN collected N frames at X fps for N sec." line every chunkLengthInSec:

	Recording 3:00 · Camera0 10,800 · Camera1 10,800 · Camera2 10,800 frames · 60.0 fps

campy's main process draws it from counters the camera processes share with it
(MakeCounters: frames grabbed, the time of the last one, and whether the camera
is opening, grabbing or done). Every other message still prints as a line of
its own: the status line is wiped before it and drawn again under it.

  - In the main process, sys.stdout and sys.stderr are wrapped (Console): a
    write wipes the status line first, and once each stream is back at the
    start of a line, the status line is drawn again under it.
  - In a camera process, each line starts with the wipe (ChildStream), which
    clears the status line wherever it stands; the main process draws it again
    at its next tick. The camera processes learn that the line is shown from
    their environment (ENV, set by Prepare before they start).

statusLine: "never" (the default: the console is as before), "auto" (only when
stdout is a console: output redirected to a file keeps the "collected" lines),
or "always" (also into a file or pipe, console codes and all).

The wipe is a carriage return and ANSI's erase-to-end-of-line ("\\r\\x1b[K"). On
Windows the console's virtual terminal processing is turned on for it (classic
conhost and PowerShell 5 have it off); where that fails, the line is wiped
with spaces instead. The line is cut to the console's width less one, since a
line that wraps can't be rewritten in place.
"""

import os, sys, time, shutil, threading
import multiprocessing as mp

ENV = "CAMPY_STATUS_LINE" # "ansi" or "pad", then ",stderr" when stderr is wiped too
EVERY_S = 1.0 # how often the status line is drawn
RATE_S = 5.0 # the frame rate shown: over the last frames this long
QUIET_S = 1.0 # a camera with no new frame for this long has no rate
SAME_FPS = 0.5 # rates closer than this: one rate (the lowest), else each camera's
ANSI_CLEAR = "\r\x1b[K"

OPENING, GRABBING, ENDED = 0, 1, 2
FIELDS = 3 # per camera: frames grabbed, time.time() of the last one, state


# ---------------------------------------------------------------------- whether, and how


def Wanted(setting, stream=None):
	"""Whether to show it: statusLine "always", "never" or "auto" (when stream, stdout, is a console)."""
	setting = str(setting).lower()
	if setting == "always":
		return True
	if setting != "auto":
		return False
	stream = sys.stdout if stream is None else stream
	try:
		return bool(stream.isatty())
	except Exception:
		return False


def EnableVT(stream=None):
	"""
	Whether ANSI's wipe works on this console. On Windows, turns on the
	console's virtual terminal processing (it belongs to the console, so the
	camera processes, which share it, get it too).
	"""
	if os.name != "nt":
		return True
	stream = sys.stdout if stream is None else stream
	try:
		if not stream.isatty():
			return True
		import ctypes, msvcrt
		from ctypes import wintypes
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		handle = msvcrt.get_osfhandle(stream.fileno())
		mode = wintypes.DWORD()
		if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
			return False
		VT = 0x0004 # ENABLE_VIRTUAL_TERMINAL_PROCESSING
		return bool(mode.value & VT) or bool(kernel32.SetConsoleMode(handle, mode.value | VT))
	except Exception:
		return False


def Width():
	# The console's columns, less one: a line as wide as the console wraps at once on Windows
	return max(20, shutil.get_terminal_size((100, 24)).columns - 1)


def ClearText(how):
	# What wipes the line the cursor is on: ANSI, or spaces where the console has no ANSI ("pad")
	if how == "pad":
		return "\r" + " " * Width() + "\r"
	return ANSI_CLEAR


class Mode:
	def __init__(self, how, stderr):
		self.how, self.stderr = how, stderr


def Prepare(params, stdout=None, stderr=None):
	"""
	In the main process, before the camera processes start: whether the status
	line is shown, and if so how it is wiped, which the camera processes read
	from their environment (ENV). Returns that (a Mode), or None.
	"""
	stdout = sys.stdout if stdout is None else stdout
	stderr = sys.stderr if stderr is None else stderr
	setting = params.get("statusLine", "never")
	if not Wanted(setting, stdout):
		os.environ.pop(ENV, None)
		return None
	how = "ansi" if EnableVT(stdout) else "pad"
	try:
		err = str(setting).lower() == "always" or bool(stderr.isatty())
	except Exception:
		err = False
	os.environ[ENV] = how + (",stderr" if err else "")
	return Mode(how, err)


def Shown():
	"""Whether the status line is shown: then the cameras' "collected" lines aren't printed."""
	return bool(os.environ.get(ENV))


# ---------------------------------------------------------------------- the counters


_counters = None # in a camera process: the shared counters, when the status line is shown


def MakeCounters(num_cams):
	# Shared with the camera processes through the pool's initializer (campy.InitCameraProcess)
	return mp.get_context("spawn").RawArray("d", FIELDS * num_cams)


def UseCounters(counters):
	global _counters
	_counters = counters


def Count(n_cam, frames):
	# A camera process: frames grabbed so far, now
	if _counters is not None:
		_counters[FIELDS * n_cam] = frames
		_counters[FIELDS * n_cam + 1] = time.time()


def State(n_cam, state):
	if _counters is not None:
		_counters[FIELDS * n_cam + 2] = state


# ---------------------------------------------------------------------- a camera process


class ChildStream:
	"""
	A camera process's stdout (or stderr): each line it writes starts with the
	wipe, which clears the main process's status line where it stands, and
	goes out whole.
	"""

	def __init__(self, stream, how):
		self.stream, self.how = stream, how
		self.pending = ""
		self.lock = threading.RLock()

	def write(self, text):
		with self.lock:
			self.pending += text
			cut = self.pending.rfind("\n")
			if cut >= 0:
				lines, self.pending = self.pending[:cut + 1], self.pending[cut + 1:]
				self.stream.write(ClearText(self.how) + lines)
		return len(text)

	def flush(self):
		with self.lock:
			if self.pending:
				self.stream.write(ClearText(self.how) + self.pending)
				self.pending = ""
			self.stream.flush()

	def __getattr__(self, name):
		return getattr(self.stream, name)


def Child():
	"""In a camera process: when the main process shows the status line, each line wipes it first."""
	value = os.environ.get(ENV)
	if not value:
		return
	parts = value.split(",")
	if not isinstance(sys.stdout, ChildStream):
		sys.stdout = ChildStream(sys.stdout, parts[0])
	if "stderr" in parts[1:] and not isinstance(sys.stderr, ChildStream):
		sys.stderr = ChildStream(sys.stderr, parts[0])


# ---------------------------------------------------------------------- the main process


class Console:
	"""
	The main process's console with the status line at its bottom. Before a
	write, the drawn status line is wiped; once each stream has ended its
	line, it is drawn again. Every thread writes through the one lock.
	"""

	def __init__(self, out, err, how):
		self.out, self.err, self.how = out, err, how
		self.lock = threading.RLock()
		self.text = None # the status line, once there is one
		self.drawn = False
		self.midline = set() # streams whose last write did not end its line

	def Write(self, stream, text):
		if not text:
			return 0
		with self.lock:
			self.Wipe()
			real = self.err if stream == "stderr" else self.out
			real.write(text)
			if text.endswith("\n"):
				self.midline.discard(stream)
			else:
				self.midline.add(stream)
			real.flush()
			self.Redraw()
		return len(text)

	def Wipe(self):
		if self.drawn:
			self.out.write(ClearText(self.how))
			self.out.flush()
			self.drawn = False

	def Redraw(self):
		with self.lock:
			if self.text is None or self.midline:
				return
			self.out.write(ClearText(self.how) + self.text)
			self.out.flush()
			self.drawn = True

	def Draw(self, text):
		with self.lock:
			self.text = text
			self.Redraw()

	def Clear(self):
		with self.lock:
			self.Wipe()
			self.text = None


class Stream:
	"""sys.stdout or sys.stderr in the main process, while the status line is shown."""

	def __init__(self, console, name, real):
		self.console, self.name, self.real = console, name, real

	def write(self, text):
		return self.console.Write(self.name, text)

	def flush(self):
		with self.console.lock:
			self.real.flush()

	def __getattr__(self, name):
		return getattr(self.real, name)


class StatusLine:
	"""
	The main process's status line, from the camera processes' counters.
	Started as the camera processes start, stopped once they have all ended.
	clock and wall are the tests'.
	"""

	def __init__(self, mode, counters, names, clock=time.monotonic, wall=time.time):
		self.mode = mode
		self.counters = counters
		self.names = list(names)
		self.clock, self.wall = clock, wall
		self.started = None
		self.firstFrame = None # when the first frame was seen (clock)
		self.history = [[] for _ in self.names] # each camera's (frame time, frames), the last RATE_S
		self.sep = Separator(getattr(sys.stdout, "encoding", None))
		self.console = None
		self.saved = None
		self.done = threading.Event()
		self.thread = None

	def Start(self):
		self.started = self.clock()
		self.saved = (sys.stdout, sys.stderr)
		self.console = Console(sys.stdout, sys.stderr, self.mode.how)
		sys.stdout = Stream(self.console, "stdout", sys.stdout)
		if self.mode.stderr:
			sys.stderr = Stream(self.console, "stderr", sys.stderr)
		self.Tick()
		self.thread = threading.Thread(target=self.Run, name="campy status line", daemon=True)
		self.thread.start()
		return self

	def Run(self):
		while not self.done.wait(EVERY_S):
			try:
				self.Tick()
			except Exception:
				pass # the status line is only the console's: the recording goes on

	def Tick(self):
		self.console.Draw(self.Text())

	def Stop(self):
		# Wipes the status line and gives the console back
		self.done.set()
		if self.thread is not None:
			self.thread.join(2)
		if self.console is not None:
			self.console.Clear()
			if isinstance(sys.stdout, Stream):
				sys.stdout = self.saved[0]
			if isinstance(sys.stderr, Stream):
				sys.stderr = self.saved[1]
			self.console = None

	def Row(self, c):
		f = FIELDS * c
		return {"frames": int(self.counters[f]), "frameTime": self.counters[f + 1], "state": int(self.counters[f + 2])}

	def Text(self):
		now, wall = self.clock(), self.wall()
		rows = [self.Row(c) for c in range(len(self.names))]
		rates = [self.Rate(c, row, wall) for c, row in enumerate(rows)]
		if self.firstFrame is None and any(row["frames"] > 0 for row in rows):
			self.firstFrame = now
		if self.firstFrame is None:
			head = "Waiting for the first frame {}".format(Clock(now - self.started))
		else:
			head = "Recording {}".format(Clock(now - self.firstFrame))
		tail = []
		shown = [r for r in rates if r is not None]
		if shown:
			if max(shown) - min(shown) < SAME_FPS:
				tail.append("{:.1f} fps".format(min(shown)))
			else:
				tail.append("fps " + "/".join("{:.1f}".format(r) if r is not None else "-" for r in rates))
		else:
			grabbing = [row for row in rows if row["state"] == GRABBING and row["frames"] > 0]
			if grabbing and all(wall - row["frameTime"] >= QUIET_S for row in grabbing):
				tail.append("no new frames for {}".format(Clock(wall - max(row["frameTime"] for row in grabbing))))
		return self.Fit(head, rows, tail)

	def Fit(self, head, rows, tail):
		# The names with their counts, or the counts alone where they don't fit, cut as a last resort
		def counts(named):
			# Named: "Camera0 opening", "Camera0 ended at 800", "Camera0 238";
			# "frames" follows the list when a camera is recording
			parts, running = [], False
			for name, row in zip(self.names, rows):
				count = "{:,}".format(row["frames"])
				if row["state"] == OPENING:
					parts.append("{} opening".format(name) if named else count + " (opening)")
				elif row["state"] == ENDED:
					parts.append("{} ended at {}".format(name, count) if named else count + " (ended)")
				else:
					running = True
					parts.append("{} {}".format(name, count) if named else count)
			if not named:
				return "frames " + " / ".join(parts)
			return self.sep.join(parts) + (" frames" if running else "")
		width = Width()
		for named in (True, False):
			text = self.sep.join([head, counts(named)] + tail)
			if len(text) <= width:
				return text
		return text[:width - 3] + "..."

	def Rate(self, c, row, wall):
		"""
		Camera c's frames a second over its last RATE_S of frames, by the times
		they arrived: none for a camera with no new frame for QUIET_S.
		"""
		history = self.history[c]
		if row["frames"] <= 0 or row["state"] != GRABBING or wall - row["frameTime"] >= QUIET_S:
			history.clear()
			return None
		if not history or history[-1] != (row["frameTime"], row["frames"]):
			history.append((row["frameTime"], row["frames"]))
		while len(history) > 2 and history[-1][0] - history[1][0] >= RATE_S:
			history.pop(0)
		(t0, n0), (t1, n1) = history[0], history[-1]
		if t1 <= t0 or n1 <= n0:
			return None
		return (n1 - n0) / (t1 - t0)


class Separator:
	# A middle dot, or a bar where the console's encoding has none
	def __init__(self, encoding):
		try:
			"·".encode(encoding or "utf-8")
			self.sep = " · "
		except Exception:
			self.sep = " | "

	def join(self, parts):
		return self.sep.join(parts)


def Clock(seconds):
	# 3:00, 1:02:03, 2d 01:02:03
	seconds = max(0, int(seconds))
	days, seconds = divmod(seconds, 86400)
	hours, seconds = divmod(seconds, 3600)
	minutes, seconds = divmod(seconds, 60)
	if days:
		return "{}d {:02d}:{:02d}:{:02d}".format(days, hours, minutes, seconds)
	if hours:
		return "{}:{:02d}:{:02d}".format(hours, minutes, seconds)
	return "{}:{:02d}".format(minutes, seconds)
