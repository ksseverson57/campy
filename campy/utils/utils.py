import signal
import sys
import queue
import logging
import threading


def Say(text):
	"""
	Prints text and its newline in one write, then flushes. Each camera runs in a
	process of its own and they all print at the same time; print() writes its
	text, each separator and the newline separately, so lines from different
	cameras could splice together ("Camera0Camera1 ready to trigger.").
	In a camera process, the printer thread writes it (StartPrinter).
	"""
	line = "{}\n".format(text)
	if _printer is not None:
		_printer.Put("stdout", line)
	else:
		Write("stdout", line)


def Write(stream, line):
	out = sys.stderr if stream == "stderr" else sys.stdout
	out.write(line)
	out.flush()


class Printer:
	"""
	Writes what a camera process says from a thread of its own, so the thread
	grabbing frames never waits on a slow console or log file. Messages go out
	in the order they were said, one write each, stdout and stderr (logging)
	alike. Put never blocks, even from a signal handler (SimpleQueue).
	"""

	def __init__(self):
		self.queue = queue.SimpleQueue()
		self.thread = threading.Thread(target=self.Run, name="campy printer", daemon=True)
		self.thread.start()

	def Put(self, stream, line):
		self.queue.put((stream, line))

	def Run(self):
		while True:
			item = self.queue.get()
			if item is None:
				return
			try:
				Write(*item)
			except Exception:
				pass # a console that is gone: the rest are still tried

	def Stop(self):
		# Writes everything said so far, then ends the thread
		self.queue.put(None)
		self.thread.join()


class PrinterHandler(logging.Handler):
	# logging's messages, through the printer to stderr, in order with Say's.
	# As logging writes them with no handler set up: WARNING and up, the
	# message (and traceback) alone.
	def __init__(self, printer):
		logging.Handler.__init__(self, logging.WARNING)
		self.printer = printer

	def emit(self, record):
		try:
			self.printer.Put("stderr", self.format(record) + "\n")
		except Exception:
			self.handleError(record)


_printer = None
_handler = None


def StartPrinter():
	"""
	From here on, Say and logging (when it has no handler of its own) are
	written by a printer thread. Each camera process starts one, and stops it
	as it ends (StopPrinter), which writes whatever is left.
	"""
	global _printer, _handler
	if _printer is not None:
		return _printer
	_printer = Printer()
	root = logging.getLogger()
	if not root.handlers:
		_handler = PrinterHandler(_printer)
		root.addHandler(_handler)
	return _printer


def StopPrinter():
	# Writes everything said so far; Say writes directly again
	global _printer, _handler
	printer, _printer = _printer, None
	if _handler is not None:
		logging.getLogger().removeHandler(_handler)
		_handler = None
	if printer is not None:
		printer.Stop()


class QueueKeyboardInterrupt(object):
	'''
	Usage:
	from campy.utils.utils import HandleKeyboardInterrupt

	with QueueKeyboardInterrupt(queue):
		# stuff here will not be interrupted by SIGINT
		<critical_code()>
	'''
	def __init__(self, object):
		# Insert queue object into keyboard interrupt handler for signaling
		self.queue = object["queue"]
		self.message = object["message"]

	def __enter__(self):
		self.signal_received = False
		self.old_handler = signal.signal(signal.SIGINT, self.handler)
				
	def handler(self, sig, frame):
		self.signal_received = (sig, frame)
		Say('SIGINT received. KeyboardInterrupt has been queued.')
		self.queue.append(self.message)
	
	def __exit__(self, type, value, traceback):
		pass

class HandleKeyboardInterrupt:
	'''
	Usage:
	from campy.utils.utils import HandleKeyboardInterrupt

	with HandleKeyboardInterrupt(queue):
		# stuff here will not be interrupted by SIGINT
		<critical_code()>
	'''
	def __init__(self):
		pass

	def __enter__(self):
		self.signal_received = False
		self.old_handler = signal.signal(signal.SIGINT, self.handler)
				
	def handler(self, sig, frame):
		self.signal_received = (sig, frame)
		Say('SIGINT received. KeyboardInterrupt has been handled.')
	
	def __exit__(self, type, value, traceback):
		pass