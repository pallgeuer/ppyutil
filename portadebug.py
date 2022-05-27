# Portalocker debugging utilities
# To automatically enable debugging of all portalocker file locking that is happening,
# just import this module PRIOR to importing the portalocker module, and you're ready.

# Imports
import sys
import functools
import util.print
_auto_enable_debug = 'portalocker' not in sys.modules
import portalocker

# Set up debugging of portalocker file locking
def debug_porta_lock():
	debug_porta_lock_fn()
	debug_porta_lock_cls()

# Set up debugging of portalocker file locking by intercepting all calls to the portalocker lock function
def debug_porta_lock_fn():  # Note: This does not intercept calls to the lock function from inside the portalocker module itself
	portalocker._raw_lock = portalocker.lock
	# noinspection PyProtectedMember, PyUnresolvedReferences
	@functools.wraps(portalocker._raw_lock)
	def wrapped_lock(file_, flags, *args, **kwargs):
		util.print.print_debug(f"Applying flock: {file_.name} ({lock_flags_str(flags)})")
		return portalocker._raw_lock(file_, flags, *args, **kwargs)
	portalocker.lock = wrapped_lock

# Set up debugging of lock acquisition/releasing by monkey patching the portalocker Lock class
# noinspection PyProtectedMember
def debug_porta_lock_cls():

	portalocker.Lock._raw_acquire = portalocker.Lock.acquire
	# noinspection PyProtectedMember
	@functools.wraps(portalocker.Lock._raw_acquire)
	def wrapped_acquire(self, *args, **kwargs):
		util.print.print_debug(f"Acquiring lock: {self.filename}")
		return portalocker.Lock._raw_acquire(self, *args, **kwargs)
	portalocker.Lock.acquire = wrapped_acquire

	portalocker.Lock._raw_release = portalocker.Lock.release
	# noinspection PyProtectedMember, PyArgumentList
	@functools.wraps(portalocker.Lock._raw_release)
	def wrapped_release(self, *args, **kwargs):
		util.print.print_debug(f"Releasing lock: {self.filename}")
		return portalocker.Lock._raw_release(self, *args, **kwargs)
	portalocker.Lock.release = wrapped_release

	portalocker.Lock._raw_get_lock = portalocker.Lock._get_lock
	# noinspection PyProtectedMember, PyArgumentList
	@functools.wraps(portalocker.Lock._raw_get_lock)
	def wrapped_get_lock(self, fh, *args, **kwargs):
		util.print.print_debug(f"Applying flock: {fh.name} ({lock_flags_str(self.flags)})")
		return portalocker.Lock._raw_get_lock(self, fh, *args, **kwargs)
	portalocker.Lock._get_lock = wrapped_get_lock

# Convert an integer set of flags to a string representation
def lock_flags_str(flags):
	tags = []
	for flag, tag in ((portalocker.LOCK_EX, 'EX'), (portalocker.LOCK_SH, 'SH'), (portalocker.LOCK_NB, 'NB'), (portalocker.LOCK_UN, 'UN')):
		if flags & flag:
			tags.append(tag)
	return '|'.join(tags) if tags else 'NONE'

# Automatically enable debug mode if portalocker was already imported
if _auto_enable_debug:
	debug_porta_lock()
# EOF
