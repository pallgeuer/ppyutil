# File I/O utilities

# Imports
import os
import contextlib

# Context manager that temporarily changes the process umask (user file mode creation mask)
@contextlib.contextmanager
def change_umask(umask):
	# umask = Process umask to temporarily set, e.g. 0o002 (None => Don't touch the current process umask)
	orig_umask = None
	try:
		if umask is not None:
			orig_umask = os.umask(umask)
		yield umask
	finally:
		if orig_umask is not None:
			os.umask(orig_umask)

# Custom file opener class (to be used with the opener keyword argument of the open() builtin)
class FileOpener:

	def __init__(self, set_flags=None, unset_flags=None, mode=None, umask=None):
		# set_flags = OR-ed flags to set for opening of the file (e.g. os.O_CREAT => see https://docs.python.org/3/library/os.html#os.open)
		# unset_flags = OR-ed flags to unset for opening of the file (flags that are present in both set_flags and unset_flags end up being set)
		# mode = Mode to create the file with, if applicable (permissions bits, the current umask will still be unset from this value)
		# umask = If given, set this explicit umask while opening the file
		self.set_flags = set_flags
		self.unset_flags = unset_flags
		self.mode = mode if mode is not None else 0o666  # Default mode used by open() => https://github.com/python/cpython/blob/20c22db602bf2a51f5231433b9054290f8069b90/Lib/_pyio.py#L1561
		self.umask = umask

	def __call__(self, file, flags):
		if self.unset_flags:
			flags &= ~self.unset_flags
		if self.set_flags:
			flags |= self.set_flags
		with change_umask(self.umask):
			fd = os.open(file, flags, self.mode)
		return fd
# EOF
