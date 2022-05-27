# Standard output/error tee utilities

# Imports
import io
import sys
import weakref
import traceback

# Tee standard output/error to a file
class StdTee:
	# The preferred use of this class is with the 'with' statement, e.g.
	#
	#     with StdTee('my_file.log'):
	#         ...
	#
	#     tee = StdTee('another_file.log')
	#     with tee: # <-- By default initially overwrites and starts with empty file
	#         ...
	#     ... # <-- Code unaffected by StdTee
	#     with tee: # <-- By default appends to the file in all subsequent with-blocks
	#         ...
	#
	#     with tee.set_append(False): # <-- Overwrites and starts from an empty file again
	#         ...
	#     with tee.set_file_path('alternative.log'): # <-- Changes destination file
	#         ...
	#
	#     with StdTee('my_file.log') as log:
	#         print("This is only in the log", file=log)
	#     with tee as log: # <-- Assigns tee.file to log, NOT tee itself
	#         print("This is only in the log", file=log)
	#         tee.file.write("Also just in log\n")
	#
	# 'With' statements play nice with exceptions in that StdTee is immediately disabled when an exception is raised
	# inside a with-block, PRIOR to any possible handling of the exception by code external to the with-block.
	# Note however that as a feature, StdTee writes the exception traceback that occurred to the opened file before
	# closing it, even if the exception is ultimately caught and handled external to the with-block (disable using
	# tee_exc_tb). It is written to file because it explains/documents why the tee-to-file stopped at the point it did.
	#
	# The non-preferred use of this class is with explicit start/stop calls:
	#
	#     tee = StdTee('my_file.log')
	#     tee.start()
	#     ...
	#     tee.stop()
	#
	# More than likely, if you THINK you need this solution, then what you're really looking for is contextlib.ExitStack!
	#
	# Most people right now would be having a heart attack about exception safety, but it's not QUITE as bad as it seems.
	# MOST of the time it will still act appropriately, and if file_line_buffered is set to True, whatever lines have been
	# tee-ed so far are guaranteed to already be in the target file. If an exception is raised between start() and stop(),
	# StdTee will keep doing its job until it is deleted (this is not guaranteed to actually happen though under certain
	# circumstances involving program termination), at which point cleanup will generally occur just fine. Thus, most
	# frequently, the only side-effect of not using the more robust 'with' statement is that everything between raising
	# the exception and deleting the StdTee object will get 'unexpectedly' tee-ed as well. If the exception is unhandled
	# or handled in a parent function, then 'tee' going out of scope cleans up after itself at EARLIEST only AFTER the
	# exception handler has finished (as the life of the tee object is prolonged by the reference to it created as part of
	# the exception traceback). Reference cycles and delayed garbage collection have the possibility of delaying the clean
	# up action, even though StdTee attempts to avoid causing this situation itself by internally using weakrefs.
	# In summary, just don't go around saving StdTee objects as globals or in objects that don't go out of scope when an
	# exception is handled and for the most part you'll be fine. You can also explicitly 'del tee' if required for some
	# inline situations, but ultimately, if you need robust code then you HAVE to use the 'with' solution.
	#
	# You can choose whether to tee stdout and/or stderr, so by nesting 'with' statements you can also tee both at the
	# same time, but to separate files. If you experience stdout/stderr lines that get mixed up in terms of their
	# chronological order, you can try auto_flush=True. Note that it is impossible for the content tee-ed to file to
	# end up out of order, so this applies to the original stdout/stderr targets only. If performance is an issue, you
	# can disable line buffering of the file (enabled by default), but then you have to be aware that sending SIGKILL
	# (e.g. Stop button in PyCharm) to the process can leave output lines missing from the file.

	def __init__(self, file_path, append=False, tee_stdout=True, tee_stderr=True, tee_exc_tb=True, auto_flush=False, file_line_buffered=True):

		self.file_path = file_path
		self.append = append
		self.tee_stdout = tee_stdout
		self.tee_stderr = tee_stderr
		self.tee_exc_tb = tee_exc_tb
		self.auto_flush = auto_flush
		self.file_line_buffered = file_line_buffered

		self._file = None
		self._redirected = False
		self._stdout = None
		self._stderr = None
		self._teeout = None
		self._teeerr = None
		self._flushout = False
		self._flusherr = False

	def __del__(self):
		self._restore_std()
		self._close_file()

	def set_file_path(self, file_path, append=False):
		self.file_path = file_path
		self.append = append
		return self

	def set_append(self, append):
		self.append = append
		return self

	def _open_file(self):
		self._file = open(self.file_path, 'a' if self.append else 'w', buffering=1 if self.file_line_buffered else -1)

	def _close_file(self):
		if self._file:
			self._file.close()
		self._file = None

	@property
	def file(self):
		if not self._file:
			raise LookupError(f"No file is active => File pointer can only be queried when {self.__class__.__name__} is currently active")
		return self._file

	def _redirect_std(self):
		if self.tee_stdout:
			self._stdout = sys.stdout
			self._teeout = self._Out(self, self._stdout)
			sys.stdout = self._teeout
			if self.auto_flush:
				self._stdout.flush()
		self._flushout = False
		if self.tee_stderr:
			self._stderr = sys.stderr
			self._teeerr = self._Err(self, self._stderr)
			sys.stderr = self._teeerr
			if self.auto_flush:
				self._stderr.flush()
		self._flusherr = False
		self._redirected = True

	def _restore_std(self):
		if self._stdout is not None and self._teeout is not None and sys.stdout is self._teeout:
			if self.auto_flush and self._flushout:
				self._stdout.flush()
			sys.stdout = self._stdout
		self._stdout = None
		self._teeout = None
		self._flushout = False
		if self._stderr is not None and self._teeerr is not None and sys.stderr is self._teeerr:
			if self.auto_flush and self._flusherr:
				self._stderr.flush()
			sys.stderr = self._stderr
		self._stderr = None
		self._teeerr = None
		self._flusherr = False
		self._redirected = False

	def __enter__(self):
		self._open_file()
		self._redirect_std()
		return self._file

	def __exit__(self, exc_type, exc_val, exc_tb):
		self._restore_std()
		if self.tee_exc_tb and exc_type is not None:
			traceback.print_exception(exc_type, exc_val, exc_tb, file=self._file)
		self._close_file()
		self.append = True
		return False

	def start(self):
		return self.__enter__()

	def stop(self):
		self.__exit__(None, None, None)

	# noinspection PyProtectedMember
	class _Out:
		def __init__(self, tee, stream):
			self.tee_ref = weakref.ref(tee)
			self.stream = stream

		def write(self, data):
			tee = self.tee_ref()
			tee and tee._write_out(data)

		def writelines(self, lines):
			tee = self.tee_ref()
			tee and tee._writelines_out(lines)

		def flush(self):
			tee = self.tee_ref()
			tee and tee._flush_out()

		def __getattr__(self, attr):
			return getattr(self.stream, attr)

	# noinspection PyProtectedMember
	class _Err:
		def __init__(self, tee, stream):
			self.tee_ref = weakref.ref(tee)
			self.stream = stream

		def write(self, data):
			tee = self.tee_ref()
			tee and tee._write_err(data)

		def writelines(self, lines):
			tee = self.tee_ref()
			tee and tee._writelines_err(lines)

		def flush(self):
			tee = self.tee_ref()
			tee and tee._flush_err()

		def __getattr__(self, attr):
			return getattr(self.stream, attr)

	@property
	def _stdout_safe(self):
		return self._stdout or sys.stdout

	@property
	def _stderr_safe(self):
		return self._stderr or sys.stderr

	@property
	def _file_open(self):
		return self._file and not self._file.closed

	def _writing_to_out(self):
		if self.auto_flush:
			if self._flusherr:
				self._stderr_safe.flush()
				self._flusherr = False
			self._flushout = True

	def _writing_to_err(self):
		if self.auto_flush:
			if self._flushout:
				self._stdout_safe.flush()
				self._flushout = False
			self._flusherr = True

	def _write_out(self, data):
		self._writing_to_out()
		self._stdout_safe.write(data)
		if self._file_open:
			self._file.write(data)

	def _write_err(self, data):
		self._writing_to_err()
		self._stderr_safe.write(data)
		if self._file_open:
			self._file.write(data)

	def _writelines_out(self, lines):
		self._writing_to_out()
		self._stdout_safe.writelines(lines)
		if self._file_open:
			self._file.writelines(lines)

	def _writelines_err(self, lines):
		self._writing_to_err()
		self._stderr_safe.writelines(lines)
		if self._file_open:
			self._file.writelines(lines)

	def _flush_out(self):
		self._stdout_safe.flush()
		if self._file_open:
			self._file.flush()
		self._flushout = False

	def _flush_err(self):
		self._stderr_safe.flush()
		if self._file_open:
			self._file.flush()
		self._flusherr = False

# Tee standard output/error to an in-memory string
class StdTeeString(StdTee):
	# The preferred use of this class is with the 'with' statement, e.g.
	#
	#     string_tee = StdTeeString()
	#     with string_tee:
	#         ...
	#     tee_value = string_tee.value(clear=False) # <-- Does not clear what has been accumulated so far
	#     ...
	#     with string_tee: # <-- Continue tee-ing to string where we left off
	#         ...
	#         so_far = string_tee.value() # <-- Inside with-block so NEVER clears the internal value
	#         ...
	#     tee_value = string_tee.value() # <-- Clears the value after returning it
	#     ...
	#     with string_tee: # <-- Start recording afresh again
	#         ...
	#     tee_value = string_tee.value()
	#
	# All other peculiarities and variants of how this class can be used are analogous to the StdTee class.

	def __init__(self, append=False, tee_stdout=True, tee_stderr=True, tee_exc_tb=True, auto_flush=False):
		super().__init__(None, append=append, tee_stdout=tee_stdout, tee_stderr=tee_stderr, tee_exc_tb=tee_exc_tb, auto_flush=auto_flush)

	def set_file_path(self, *args, **kwargs):
		raise NotImplementedError(f"{self.__class__.__name__} has no file path to set")

	def _open_file(self):
		if not self._file or not self.append:
			super()._close_file()
			self._file = io.StringIO()

	def _close_file(self):
		pass

	@property
	def file(self):
		if not self._file:
			raise LookupError(f"No string is currently being recorded => String file object can only be queried when {self.__class__.__name__} is currently active")
		return self._file

	def value(self, clear=True):
		if self._file:
			value = self._file.getvalue()
			if clear and not self._redirected:
				super()._close_file()
			return value
		else:
			return None
# EOF
