# Class utilities

# Imports
import multiprocessing

# Convenience wrapper of multiprocessing pool class to allow inline execution (processes = 0)
class Pool:

	def __init__(self, processes=None, **kwargs):
		if processes is not None and processes < 1:
			self._pool = None
			self.processes = 0
			self.parallelism = 1
		else:
			self._pool = multiprocessing.Pool(processes=processes, **kwargs)
			self.processes = processes
			self.parallelism = processes

	def __enter__(self):
		if self._pool:
			self._pool.__enter__()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		if self._pool:
			return self._pool.__exit__(exc_type, exc_val, exc_tb)
		return False

	def map(self, func, iterable, **kwargs):
		if self._pool:
			return self._pool.map(func, iterable, **kwargs)
		else:
			return list(map(func, iterable))

	def imap(self, func, iterable, **kwargs):
		if self._pool:
			return self._pool.imap(func, iterable, **kwargs)
		else:
			return list(map(func, iterable))
# EOF
