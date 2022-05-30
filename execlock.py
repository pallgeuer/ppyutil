# Execution locking utilities

# Imports
import os
import os.path
import sys
import time
import contextlib
import dataclasses
from types import MethodType
from typing import Optional, List, Set
from property_cached import cached_property
import portalocker
import psutil
import ppyutil.fileio
import ppyutil.string
from ppyutil.string import ranged_int
import ppyutil.contextman

# Constants
SYSLOCK_PATH = "/var/lock/syslock"
DEFAULT_TIMEOUT = 8
DEFAULT_CHECK_INTERVAL = 0.4

#
# Helpers
#

# Execution locking error class
class ExecLockError(Exception):
	pass

# Process ID metaclass
class ProcessIDMeta(type):

	@staticmethod
	def from_pid(pid):
		try:
			# noinspection PyProtectedMember, PyUnresolvedReferences
			ident = psutil.Process(pid)._ident
		except psutil.Error as e:
			raise OSError(f"Failed to retrieve ProcessID for PID {pid}: {e}") from None
		ctime = None
		if ident[1]:
			ctime = round(ident[1] * 1000)
		return ProcessID(pid=int(ident[0]), ctime=ctime)

	@cached_property
	def ours(cls):
		return cls.from_pid(os.getpid())

# Process ID class
@dataclasses.dataclass(frozen=True)
class ProcessID(metaclass=ProcessIDMeta):
	pid: int              # Process identifier (PID)
	ctime: Optional[int]  # Process creation time in units of milliseconds since the epoch in UTC

	def __eq__(self, other):
		if self.__class__ is other.__class__:
			return self.pid == other.pid and (self.ctime == other.ctime or (not self.ctime and not other.ctime))
		return NotImplemented

	def __hash__(self):
		return hash((self.pid, self.ctime if self.ctime else None))

# Counted lock status class
@dataclasses.dataclass(frozen=True)
class CLockStatus:
	locked: bool
	processes: Set[ProcessID]
	our_max_count: int
	max_count: int
	fill_count: int
	free_count: int

# Run lock status class
@dataclasses.dataclass(frozen=True)
class RunLockStatus:
	processes: Set[ProcessID]
	lock: List[Optional[CLockStatus]]
	base_lockable: bool
	solo_lockable: bool

# Helper function for named locks
def named_lock_path(lock_name, relative_to=SYSLOCK_PATH):
	# lock_name = Name of the required named lock
	# relative_to = Path relative to which to resolve the named lock path (None => None)
	# Return the named lock path
	if lock_name is None:
		return None
	return os.path.join(relative_to, 'named', ppyutil.string.ensure_filename(lock_name + '.lock'))

# Check whether the process is currently exiting
def process_exiting():
	exc_type = sys.exc_info()[0]
	return exc_type is not None and issubclass(exc_type, (KeyboardInterrupt, SystemExit))

#
# Standard locking
#

# Context manager that allows system-wide code execution locking (via locking of a specified system-wide file)
class ExecutionLock(metaclass=ppyutil.contextman.ReentrantMeta):

	def __init__(self, lock_path, relative_to=SYSLOCK_PATH, makedirs=True, dir_mode=0o777, file_mode=0o666, umask=0o000, blocking=True, timeout=DEFAULT_TIMEOUT, check_interval=DEFAULT_CHECK_INTERVAL, shared_lock=False, lock_delay=0):
		# lock_path = Path of the desired system-wide lock file that should govern the code execution lock (global absolute path, or path relative to relative_to, or None)
		# relative_to = Absolute directory relative to which to resolve lock_path, if lock_path is a relative path (None => Default)
		# makedirs = Whether to recursively create the required lock file directory if it doesn't exist (None => Default)
		# dir_mode = Mode to use for directory creation, up to subsequent restriction by the process umask
		# file_mode = Mode to use for lock file creation, up to subsequent restriction by the process umask
		# umask = Process umask to temporarily set while opening/creating files/directories for the lock file (None => Use current process umask without change)
		# blocking = Whether acquisition of the lock should be indefinitely blocking (True), or use a timeout (False)
		# timeout = Timeout to use for lock acquisition (seconds)
		# check_interval = Time interval to wait between repeated lock acquisition attempts (seconds)
		# shared_lock = Whether to acquire a shared lock instead of an exclusive lock
		# lock_delay = Time interval to wait before returning from __enter__ AFTER the lock has been successfully acquired (can be used to add a temporal safety margin between system-wide executions)

		self._dir_mode = dir_mode
		self._file_mode = file_mode
		self._umask = umask
		self.blocking = blocking
		self.timeout = timeout
		self.check_interval = check_interval
		self.shared_lock = shared_lock
		self._is_shared = self.shared_lock
		self.lock_delay = lock_delay if lock_delay > 0 else 0

		self._our_pid = os.getpid()
		self._our_str = f"{self._our_pid:10d}\n"  # This lock file content is compliant with the Linux Filesystem Hierarchy Standard (FHS) 3.0 for /var/lock
		self._file_opener = ppyutil.fileio.FileOpener(set_flags=os.O_DSYNC, mode=self._file_mode, umask=self._umask)

		self._relative_to = SYSLOCK_PATH
		self._makedirs = True
		self._lock_path = None
		self._lock = None

		if relative_to is None:
			relative_to = self._relative_to
		self.set_lock_path(lock_path, relative_to=relative_to, makedirs=makedirs)

	def set_lock_path(self, lock_path, relative_to=None, makedirs=None):

		# noinspection PyUnresolvedReferences
		if self.locked or self._enter_count > 0:
			raise ExecLockError(f"Cannot set lock path while {self.__class__.__name__} is locked/entered: Tried {self._lock_path} --> {lock_path}")

		if relative_to is not None:
			if not os.path.isabs(relative_to):
				raise ExecLockError(f"Parameter 'relative_to' must be an absolute path: {relative_to}")
			self._relative_to = relative_to

		if makedirs is not None:
			self._makedirs = makedirs

		if lock_path is None:
			self._lock_path = None
			self._lock = None
		else:
			self._lock_path = os.path.join(self._relative_to, lock_path)
			if self._makedirs:
				with ppyutil.fileio.change_umask(self._umask):
					os.makedirs(os.path.dirname(self._lock_path), mode=self._dir_mode, exist_ok=True)
			self._lock = portalocker.Lock(filename=self._lock_path, mode='w', opener=self._file_opener)

	def __repr__(self):
		return f"{self.__class__.__name__}(path={self._lock_path}, pid={self._our_pid}, exclusive={not self.shared_lock})"

	@property
	def lock_path(self):
		return self._lock_path

	@property
	def lock_valid(self):
		return bool(self._lock)

	@property
	def locked(self):
		return bool(self._lock and self._lock.fh)

	@property
	def is_shared(self):
		return self._is_shared

	def set_timeout(self, timeout, check_interval, blocking=False):
		self.timeout = timeout
		self.check_interval = check_interval
		self.blocking = blocking

	def __enter__(self):

		if not self._lock:
			raise ExecLockError(f"Cannot lock {self.__class__.__name__} with a lock path of None")

		with contextlib.ExitStack() as stack:

			self._is_shared = self.shared_lock
			self._configure_lock(self._is_shared)

			start_time = time.perf_counter()
			while True:

				try:
					stack.enter_context(self._lock)
				except portalocker.LockException:
					raise ExecLockError(f"Timed out while acquiring lock: {self._lock_path}") from None

				with contextlib.suppress(OSError):  # The file self._lock.fh.name (accessed by path, as opposed to via the previously opened file descriptor) may not exist if it was deleted since we opened it => This would allow others to lock the file path even though we think we have the lock
					if os.stat(self._lock.fh.fileno()).st_ino == os.stat(self._lock.fh.name).st_ino:  # The open file descriptor we have has the same inode as accessing the corresponding locked file by path => All good, we have a truly exclusive lock
						break

				stack.close()
				time.sleep(self._lock.check_interval)
				if not self.blocking:
					self._lock.timeout = start_time + self.timeout - time.perf_counter()

			if not self._is_shared:
				self._lock.fh.write(self._our_str)
				self._lock.fh.flush()

			if self.lock_delay > 0:
				time.sleep(self.lock_delay)

			stack.pop_all()  # If execution has reached this point then everything is okay, so remove all callbacks from the ExitStack without calling them

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		if self._lock:
			self._delete_lock_file(self._is_shared)
			self._lock.__exit__(exc_type, exc_val, exc_tb)

	def ensure_locked(self, lock, during_exit=False):
		if lock and not self.locked and (during_exit or not process_exiting()):
			self.__enter__()
		if not lock and self.locked:
			self.__exit__(None, None, None)

	def _configure_lock(self, is_shared):
		self._lock.flags = portalocker.LOCK_SH if is_shared else portalocker.LOCK_EX
		self._lock.check_interval = self.check_interval
		if self.blocking:
			self._lock.timeout = 0
		else:
			self._lock.timeout = self.timeout
			self._lock.flags |= portalocker.LOCK_NB
		self._lock.fail_when_locked = False

	def _delete_lock_file(self, is_shared):
		if self._lock and self._lock.fh and not is_shared:  # It is only safe to delete the lock file if it is currently locked
			with contextlib.suppress(OSError):
				os.unlink(self._lock.fh.name)  # Delete the locked file (the file path remains locked however until the file descriptor is closed)

	def test_lockable(self, shared_lock=None):

		if not self._lock:
			raise ExecLockError(f"Cannot test lockability of {self.__class__.__name__} with a lock path of None")
		if self._lock.fh:
			return True

		if shared_lock is None:
			shared_lock = self.shared_lock
		self._lock.flags = portalocker.LOCK_SH if shared_lock else portalocker.LOCK_EX
		self._lock.flags |= portalocker.LOCK_NB

		try:
			self._lock.acquire(timeout=0, check_interval=0, fail_when_locked=True)
		except (portalocker.LockException, portalocker.AlreadyLocked):
			lockable = False
		else:
			lockable = True
		finally:
			self._delete_lock_file(shared_lock)
			self._lock.release()

		return lockable

	def touch_lock(self, shared_lock=None):

		if not self._lock:
			raise ExecLockError(f"Cannot touch {self.__class__.__name__} with a lock path of None")

		if shared_lock is None:
			shared_lock = self.shared_lock

		if self._lock.fh:
			if shared_lock == self.shared_lock:
				return
			else:
				raise ExecLockError(f"Cannot touch lock while it is already locked in the opposite configuration: {self._lock_path}")

		self._configure_lock(shared_lock)

		try:
			self._lock.acquire()
		except portalocker.LockException:
			raise ExecLockError(f"Timed out while touching lock: {self._lock_path}") from None
		finally:
			self._delete_lock_file(shared_lock)
			self._lock.release()

# Context manager that allows named system-wide code execution locking
class NamedLock(ExecutionLock):

	def __init__(self, lock_name, **kwargs):
		# lock_name = String specifying the system-wide lock name to acquire (or None)
		# kwargs = See ExecutionLock.__init__
		super().__init__(None, relative_to=SYSLOCK_PATH, makedirs=True, **kwargs)
		self.set_lock_name(lock_name)

	def set_lock_name(self, lock_name):
		lock_abspath = named_lock_path(lock_name, relative_to=SYSLOCK_PATH)
		self.set_lock_path(lock_abspath, relative_to=SYSLOCK_PATH, makedirs=True)

#
# Counted locking
#

# Context manager that allows counted system-wide code execution locking (via locking of a specified system-wide file)
class ExecutionCLock(metaclass=ppyutil.contextman.ReentrantMeta):

	def __init__(self, lock_path, max_count, relative_to=SYSLOCK_PATH, makedirs=True, dir_mode=0o777, file_mode=0o666, umask=0o000, blocking=True, timeout=DEFAULT_TIMEOUT, check_interval=DEFAULT_CHECK_INTERVAL, lock_delay=0):
		# lock_path = Path of the desired system-wide lock file that should govern the counted code execution lock (global absolute path, or path relative to relative_to, or None)
		# max_count = Maximum simultaneous number of times the lock can be acquired
		# relative_to = Absolute directory relative to which to resolve lock_path, if lock_path is a relative path (None => Default)
		# makedirs = Whether to recursively create the required lock file directory if it doesn't exist (None => Default)
		# dir_mode = Mode to use for directory creation, up to subsequent restriction by the process umask
		# file_mode = Mode to use for lock file creation, up to subsequent restriction by the process umask
		# umask = Process umask to temporarily set while opening/creating files/directories for the lock file (None => Use current process umask without change)
		# blocking = Whether acquisition of the lock should be indefinitely blocking (True), or use a timeout (False)
		# timeout = Timeout to use for lock acquisition (seconds)
		# check_interval = Time interval to wait between repeated lock acquisition attempts (seconds)
		# lock_delay = Time interval to wait before returning from __enter__ AFTER the lock has been successfully acquired (can be used to add a temporal safety margin between system-wide executions)

		self.max_count = max_count
		self._dir_mode = dir_mode
		self._file_mode = file_mode
		self._umask = umask
		self.blocking = blocking
		self.timeout = timeout
		self.check_interval = check_interval
		self.lock_delay = lock_delay if lock_delay > 0 else 0

		self._our_id = ProcessID.ours
		self._our_iid = id(self)
		self._our_str = f"{self._our_id.pid} {'0' if self._our_id.ctime is None else self._our_id.ctime} {self._our_iid}"
		self._file_opener = ppyutil.fileio.FileOpener(set_flags=os.O_CREAT, mode=self._file_mode, umask=self._umask)

		self._relative_to = SYSLOCK_PATH
		self._makedirs = True
		self._lock_path = None
		self._lock_path_swp = None
		self._lock = None
		self._locked = False

		if relative_to is None:
			relative_to = self._relative_to
		self.set_lock_path(lock_path, relative_to=relative_to, makedirs=makedirs)

	def set_lock_path(self, lock_path, relative_to=None, makedirs=None):

		# noinspection PyUnresolvedReferences
		if self.locked or self._enter_count > 0:
			raise ExecLockError(f"Cannot set lock path while {self.__class__.__name__} is locked/entered: Tried {self._lock_path} --> {lock_path}")

		if relative_to is not None:
			if not os.path.isabs(relative_to):
				raise ExecLockError(f"Parameter 'relative_to' must be an absolute path: {relative_to}")
			self._relative_to = relative_to

		if makedirs is not None:
			self._makedirs = makedirs

		if lock_path is None:
			self._lock_path = None
			self._lock_path_swp = None
			self._lock = None
			self._locked = False
		else:
			self._lock_path = os.path.join(self._relative_to, lock_path)
			self._lock_path_swp = self._lock_path + '.swp'
			if self._makedirs:
				with ppyutil.fileio.change_umask(self._umask):
					os.makedirs(os.path.dirname(self._lock_path), mode=self._dir_mode, exist_ok=True)
			self._lock = portalocker.Lock(filename=self._lock_path, mode='r', opener=self._file_opener)
			self._locked = False

	def __repr__(self):
		return f"{self.__class__.__name__}(path={self._lock_path}, max_count={self._max_count}, id='{self._our_str}')"

	@property
	def lock_path(self):
		return self._lock_path

	@property
	def lock_valid(self):
		return bool(self._lock)

	@property
	def max_count(self):
		return self._max_count

	@max_count.setter
	def max_count(self, value):
		if value < 1:
			raise ExecLockError(f"Maximum simultaneous lock acquisition count must be a positive integer: {value}")
		self._max_count = value

	@property
	def locked(self):
		return self._locked

	def lock_status(self):

		if not self._lock:
			raise ExecLockError(f"Cannot get lock status for {self.__class__.__name__} with a lock path of None")

		try:
			with open(self._lock_path, 'r') as file:
				lock_contents = list(file)
			_, processes, cur_max_count, _ = self._edit_lock_contents(lock_contents, False, force_clean=True)
		except OSError:
			processes = set()
			cur_max_count = self._max_count

		if self.locked:
			processes.add(self._our_id)
		fill_count = len(processes)

		return CLockStatus(locked=self.locked, processes=processes, our_max_count=self._max_count, max_count=cur_max_count, fill_count=fill_count, free_count=cur_max_count - fill_count)

	def set_timeout(self, timeout, check_interval, blocking=False):
		self.timeout = timeout
		self.check_interval = check_interval
		self.blocking = blocking

	def __enter__(self):
		self._update_lock_file(True)
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		if self._lock:
			self._update_lock_file(False)
		return False

	def _update_lock_file(self, enter):

		if not self._lock:
			raise ExecLockError(f"Cannot update lock file for {self.__class__.__name__} with a lock path of None")

		exit_pushed = False
		with contextlib.ExitStack() as stack:

			if self.blocking:
				self._lock.timeout = 0
				self._lock.flags = portalocker.LOCK_EX
			else:
				self._lock.timeout = self.timeout
				self._lock.flags = portalocker.LOCK_EX | portalocker.LOCK_NB
			self._lock.check_interval = self.check_interval

			start_time = time.perf_counter()
			while True:
				try:
					with self._lock:

						try:
							valid_lock = (os.stat(self._lock.fh.fileno()).st_ino == os.stat(self._lock.fh.name).st_ino)
						except OSError:
							valid_lock = False

						if valid_lock:

							lock_contents = list(self._lock.fh)
							new_contents, new_processes, max_allowed, locked = self._edit_lock_contents(lock_contents, enter)

							if new_contents:
								if new_contents != lock_contents:
									try:
										with open(self._lock_path_swp, 'w', opener=self._file_opener) as fhswp:
											fhswp.writelines(new_contents)
										os.replace(self._lock_path_swp, self._lock.fh.name)
									except:  # noqa
										with contextlib.suppress(OSError):
											os.unlink(self._lock_path_swp)
										raise
								self._locked = locked
								if enter and self._locked and not exit_pushed:
									# noinspection PyTypeChecker
									stack.push(MethodType(ExecutionCLock.__exit__, self))
									exit_pushed = True
							else:
								with contextlib.suppress(OSError):
									os.unlink(self._lock.fh.name)
								self._locked = False

							if enter == self._locked:  # Note: Both sides are assumed to be bool
								break

					time.sleep(self._lock.check_interval)
					if not self.blocking:
						self._lock.timeout = start_time + self.timeout - time.perf_counter()
						if self._lock.timeout < 0:
							raise portalocker.LockException()  # Dummy exception that gets replaced by the real timeout exception below

				except portalocker.LockException:
					raise ExecLockError(f"Timed out while {'acquiring' if enter else 'releasing'} counted lock: {self._lock_path}") from None

			if enter and self.lock_delay > 0:
				time.sleep(self.lock_delay)

			stack.pop_all()

	def _edit_lock_contents(self, contents, enter, force_clean=False):

		new_contents = []
		new_processes = set()
		max_allowed = self._max_count

		for line in contents:

			parts = line.split()
			if len(parts) != 4:
				continue

			try:
				line_id = ProcessID(pid=ranged_int(parts[0], imin=0), ctime=ranged_int(parts[1], imin=0))
				line_iid = int(parts[2])
				line_max = ranged_int(parts[3], imin=1)
			except ValueError:
				continue

			if line_iid == self._our_iid and line_id == self._our_id:
				continue

			if enter or force_clean:
				try:
					if ProcessID.from_pid(line_id.pid) != line_id:
						continue
				except OSError:
					continue

			if line_max < max_allowed:
				max_allowed = line_max
			new_contents.append(line)
			new_processes.add(line_id)

		if enter and len(new_contents) < max_allowed:
			new_contents.append(f"{self._our_str} {self._max_count}\n")
			new_processes.add(self._our_id)
			locked = True
		else:
			locked = False

		return new_contents, new_processes, max_allowed, locked

# Context manager that allows named counted system-wide code execution locking
class NamedCLock(ExecutionCLock):

	def __init__(self, lock_name, max_count, **kwargs):
		# lock_name = String specifying the system-wide lock name to acquire (or None)
		# kwargs = See ExecutionCLock.__init__
		super().__init__(None, max_count, relative_to=SYSLOCK_PATH, makedirs=True, **kwargs)
		self.set_lock_name(lock_name)

	def set_lock_name(self, lock_name):
		lock_abspath = named_lock_path(lock_name, relative_to=SYSLOCK_PATH)
		self.set_lock_path(lock_abspath, relative_to=SYSLOCK_PATH, makedirs=True)

#
# Run level locking
#

# Context manager that implements generic system-wide run level code execution locking
class RunLevelLock(metaclass=ppyutil.contextman.ReentrantMeta):

	def __init__(self, lock_path, unlocked_level, base_level, run_levels, running_thres=None, solo_thres=None, relative_to=SYSLOCK_PATH, makedirs=True, dir_mode=0o777, file_mode=0o666, umask=0o000, check_interval=DEFAULT_CHECK_INTERVAL, lock_delay=0):
		# lock_path = Base path of the system-wide lock files that should govern the run level code execution lock (global absolute file path, or file path relative to relative_to, or None)
		# unlocked_level = Unique value associated with the unlocked run level
		# base_level = Unique value associated with the base run level (shared base lock is locked, but no real run level has been attained yet)
		# run_levels = Dictionary mapping all required real run levels to their respective allowed maximum simultaneous counts (insertion order determines real run level order)
		# running_thres = Run level above (and including) which this process is considered to be 'running', i.e. needs to explicitly yield if another process wishes to go solo (None => Lowest real run level)
		# solo_thres = Minimum real run level for which going solo is permitted (None => Solo mode disabled for this process)
		# relative_to = Absolute directory relative to which to resolve lock_path, if lock_path is a relative path (None => Default)
		# makedirs = Whether to recursively create the required lock file directory if it doesn't exist (None => Default)
		# dir_mode = Mode to use for directory creation, up to subsequent restriction by the process umask
		# file_mode = Mode to use for lock file creation, up to subsequent restriction by the process umask
		# umask = Process umask to temporarily set while opening/creating files/directories for the lock file (None => Use current process umask without change)
		# check_interval = Time interval to wait between repeated lock acquisition attempts (seconds)
		# lock_delay = Time interval to wait right after acquiring the lowest real run level lock or going solo (can be used to add a temporal safety margin between system-wide executions)

		self._unlocked_level = unlocked_level
		self._base_level = base_level
		if self._unlocked_level == self._base_level:
			raise ExecLockError(f"Unlocked and base levels should not have the same value: {self._unlocked_level}")
		if self._unlocked_level in run_levels:
			raise ExecLockError(f"Run levels dict should not include the unlocked level: {self._unlocked_level}")
		if self._base_level in run_levels:
			raise ExecLockError(f"Run levels dict should not include the base level: {self._base_level}")
		self._level_list = [self._unlocked_level, self._base_level, *run_levels]
		if None in self._level_list:
			raise ExecLockError("Run levels should not have the value 'None'")
		if any(isinstance(lvl, bool) for lvl in self._level_list):
			raise ExecLockError("Run levels should not have boolean values")
		if len(self._level_list) < 3:
			raise ExecLockError("Need at least one real run level")
		self._level_map = {lvl: ilvl for ilvl, lvl in enumerate(self._level_list)}

		if running_thres is None:
			self._running_ilevel = 2
		else:
			if not (running_thres == self._base_level or running_thres in run_levels):
				raise ExecLockError(f"Running threshold level must be a valid locked run level: {running_thres}")
			self._running_ilevel = self._level_map[running_thres]

		if solo_thres is None:
			self._solo_ilevel = 0
		else:
			if solo_thres not in run_levels:
				raise ExecLockError(f"Solo threshold level, if given, must be a valid real run level: {solo_thres}")
			self._solo_ilevel = self._level_map[solo_thres]
			if self._solo_ilevel < self._running_ilevel:
				raise ExecLockError(f"Solo threshold level ({solo_thres}) must be greater or equal to the running threshold level ({self._level_list[self._running_ilevel]})")

		self._ilevel_last_set = 0
		self._ilevel_cm_map = {}
		self._solo_last_set = False
		self._solo_cm_map = {}

		self._dir_mode = dir_mode
		self._file_mode = file_mode
		self._umask = umask
		self.check_interval = check_interval
		self.lock_delay = lock_delay if lock_delay > 0 else 0

		self._relative_to = SYSLOCK_PATH
		self._makedirs = True
		self._lock_path = None

		base_lock = ExecutionLock(None, relative_to=self._relative_to, makedirs=False, dir_mode=dir_mode, file_mode=file_mode, umask=umask, blocking=True, check_interval=self.check_interval, shared_lock=True, lock_delay=0)
		self._lock = [None, base_lock, *(ExecutionCLock(None, max_count, relative_to=self._relative_to, makedirs=False, dir_mode=dir_mode, file_mode=file_mode, umask=umask, blocking=True, check_interval=self.check_interval, lock_delay=0) for max_count in run_levels.values())]
		self._running_lock = ExecutionLock(None, relative_to=self._relative_to, makedirs=False, dir_mode=dir_mode, file_mode=file_mode, umask=umask, blocking=True, check_interval=self.check_interval, shared_lock=True, lock_delay=0)
		self._solo_lock = ExecutionLock(None, relative_to=self._relative_to, makedirs=False, dir_mode=dir_mode, file_mode=file_mode, umask=umask, blocking=True, check_interval=self.check_interval, shared_lock=False, lock_delay=0)

		if relative_to is None:
			relative_to = self._relative_to
		self.set_lock_path(lock_path, relative_to=relative_to, makedirs=makedirs)

	def set_lock_path(self, lock_path, relative_to=None, makedirs=None):

		if self.locked:
			raise ExecLockError(f"Cannot set lock path while {self.__class__.__name__} is locked: Tried {self._lock_path} --> {lock_path}")

		if relative_to is not None:
			if not os.path.isabs(relative_to):
				raise ExecLockError(f"Parameter 'relative_to' must be an absolute path: {relative_to}")
			self._relative_to = relative_to

		if makedirs is not None:
			self._makedirs = makedirs

		if lock_path is None:
			self._lock_path = None
			for lock in self._lock[1:]:
				lock.set_lock_path(None, relative_to=self._relative_to, makedirs=False)
			self._running_lock.set_lock_path(None, relative_to=self._relative_to, makedirs=False)
			self._solo_lock.set_lock_path(None, relative_to=self._relative_to, makedirs=False)
		else:
			self._lock_path = os.path.join(self._relative_to, lock_path)
			if self._makedirs:
				with ppyutil.fileio.change_umask(self._umask):
					os.makedirs(os.path.dirname(self._lock_path), mode=self._dir_mode, exist_ok=True)
			self._lock[1].set_lock_path(self._lock_path, relative_to=self._relative_to, makedirs=False)
			for ilvl, lock in enumerate(self._lock[2:], 2):
				lock.set_lock_path(self._lock_path + f'.{ilvl - 1}', relative_to=self._relative_to, makedirs=False)
			self._running_lock.set_lock_path(self._lock_path + '.r', relative_to=self._relative_to, makedirs=False)
			self._solo_lock.set_lock_path(self._lock_path + '.s', relative_to=self._relative_to, makedirs=False)

	def __repr__(self):
		return f"{self.__class__.__name__}(path={self._lock_path}, real_levels={len(self._level_list) - 2}, solo={'enabled' if self.solo_enabled else 'disabled'})"

	@property
	def lock_path(self):
		return self._lock_path

	@property
	def lock_valid(self):
		return self._lock_path is not None

	@property
	def locked(self):
		return self._lock[1].locked

	@property
	def solo_enabled(self):  # Note: This just determines whether THIS process can go solo => If ANY OTHER concurrent process is allowed to go solo, then this process must explicitly check/yield for solo-ers nonetheless
		return self._solo_ilevel >= 2

	@property
	def solo_possible(self):
		return self._solo_ilevel >= 2 and self._lock[self._solo_ilevel].locked

	@property
	def solo_thres(self):  # Note: If solo mode is disabled, this by default just returns the lowest real run level
		return self._level_list[max(self._solo_ilevel, 2)]

	@property
	def is_solo(self):
		return self._solo_lock.locked

	@property
	def running_thres(self):
		return self._level_list[self._running_ilevel]

	@property
	def running(self):
		return self._running_lock.locked

	@property
	def current_level(self):
		return self._level_list[self._current_ilevel()]

	def current_level_satisfies(self, level):
		return self._lock[self._level_map[level]].locked

	def _current_ilevel(self):
		ilevel = 0
		for lock in self._lock[1:]:
			if lock.locked:
				ilevel += 1
			else:
				break
		return ilevel

	def run_levels(self):
		return tuple(self._level_list[2:])

	def max_counts(self):
		return {lvl: lock.max_count for lvl, lock in zip(self._level_list[2:], self._lock[2:])}

	def update_max_counts(self, run_levels, error_if_locked=True, allow_raise=True):
		# run_levels = Dict[Run level, Max count] where only the specified run level maximum counts are updated
		# error_if_locked = Raise an error if a max count is requested to change its value while it's locked
		# allow_raise = Do not raise an error if the max count change is an increase
		for lvl, max_count in run_levels.items():
			ilvl = self._level_map[lvl]
			lock = self._lock[ilvl]
			if error_if_locked and lock.locked and max_count != lock.max_count and (max_count < lock.max_count or not allow_raise):
				raise ExecLockError(f"Invalid requested change to max count while counted lock is locked ({lock.max_count} -> {max_count}): {lock.lock_path}")
			lock.max_count = max_count

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self._set_running(False)
		self._end_solo(manage_running=False)
		self._set_ilevel(0, manage_running=False)
		return False

	# noinspection PyProtectedMember
	class LevelCM(metaclass=ppyutil.contextman.ReentrantMeta):

		def __init__(self, run_lock, level):
			self._run_lock = run_lock
			self._ilevel = self._run_lock._level_map[level]

		def __enter__(self):
			self._run_lock._set_ilevel(self._ilevel, cm=self)
			return self._run_lock

		def __exit__(self, exc_type, exc_val, exc_tb):
			self._run_lock._set_ilevel(None, cm=self)
			return False

	def level(self, level):
		return self.LevelCM(self, level)

	def set_level(self, level):
		self._set_ilevel(self._level_map[level])

	def _set_ilevel(self, ilevel, cm=None, manage_running=True):

		num_levels = len(self._level_list)
		if (ilevel is None and cm is None) or (ilevel is not None and (ilevel < 0 or ilevel >= num_levels)):
			raise ExecLockError(f"Invalid requested ilevel: {ilevel}")

		# noinspection PyChainedComparisons, PyUnresolvedReferences
		if ilevel is not None and ilevel > 0 and self._enter_count <= 0:
			raise ExecLockError(f"Need to enter the {self.__class__.__name__} context manager before setting a locked run level: {self._level_list[ilevel]}")

		if cm is None:
			self._ilevel_last_set = ilevel
			self._ilevel_cm_map.clear()
		elif ilevel is None:
			self._ilevel_cm_map.pop(cm, None)
		else:
			self._ilevel_cm_map[cm] = ilevel

		# noinspection PyTypeChecker
		new_ilevel: int = max(self._ilevel_last_set, max(self._ilevel_cm_map.values(), default=0))

		cur_ilevel = self._current_ilevel()
		self._set_ilevel_cb(cur_ilevel, new_ilevel, False)

		if self._solo_lock.locked:
			if new_ilevel != cur_ilevel:
				raise ExecLockError(f"Run level cannot be changed in solo mode")
			else:
				self._set_ilevel_cb(cur_ilevel, new_ilevel, True)
				return

		if manage_running:
			self._set_running(False)

		for ilvl in range(num_levels - 1, new_ilevel, -1):
			lock = self._lock[ilvl]
			if lock.locked:
				lock.check_interval = self.check_interval
				lock.__exit__(None, None, None)

		with contextlib.ExitStack() as stack:
			was_invalid = False
			for ilvl in range(1, new_ilevel + 1):
				lock = self._lock[ilvl]
				if not lock.locked:
					if not lock.lock_valid:
						was_invalid = True
						self._lock_invalid_cb(False)
					lock.check_interval = self.check_interval
					stack.enter_context(lock)
					if ilvl == 2 and self.lock_delay > 0:
						time.sleep(self.lock_delay)
			if was_invalid:
				self._lock_invalid_cb(True)
			stack.pop_all()

		if manage_running and new_ilevel >= self._running_ilevel:
			self._set_running(True)

		self._set_ilevel_cb(cur_ilevel, new_ilevel, True)

	def _set_ilevel_cb(self, cur_ilevel, new_ilevel, done):
		pass

	def _lock_invalid_cb(self, done):
		pass

	def _set_running(self, running, exclusive=False):
		self._running_lock.shared_lock = not exclusive
		if running and not self._running_lock.locked and not process_exiting():
			self._running_lock.__enter__()
		if not running and self._running_lock.locked:
			self._running_lock.__exit__(None, None, None)

	def lock_status(self, max_level=None):
		return self._lock_status(max_ilevel=None if max_level is None else self._level_map[max_level])

	def _lock_status(self, max_ilevel=None):

		base_lockable = self._lock[1].test_lockable()
		solo_lockable = self._solo_lock.test_lockable(shared_lock=True)

		num_levels = len(self._level_list)
		if max_ilevel is None:
			max_ilevel = num_levels

		lock_statuses: List[Optional[CLockStatus]] = [None] * num_levels
		for ilvl, lock in enumerate(self._lock[2:(max_ilevel + 1)], 2):
			lock_statuses[ilvl] = lock.lock_status()
		processes = set.union(*(lock_status.processes for lock_status in lock_statuses if lock_status is not None))

		return RunLockStatus(processes=processes, lock=lock_statuses, base_lockable=base_lockable, solo_lockable=solo_lockable)

	# noinspection PyProtectedMember
	class SoloCM(metaclass=ppyutil.contextman.ReentrantMeta):

		def __init__(self, run_lock, ensure_level=False):
			self._run_lock = run_lock
			self._ensure_ilevel = ensure_level if isinstance(ensure_level, bool) else self._run_lock._level_map[ensure_level]

		def __enter__(self):
			self._run_lock._go_solo(ensure_ilevel=self._ensure_ilevel, cm=self)
			return self._run_lock

		def __exit__(self, exc_type, exc_val, exc_tb):
			self._run_lock._end_solo(cm=self)
			return False

	def solo(self, ensure_level=False):
		return self.SoloCM(self, ensure_level=ensure_level)

	def go_solo(self, ensure_level=False):
		ensure_ilevel = ensure_level if isinstance(ensure_level, bool) else self._level_map[ensure_level]
		self._go_solo(ensure_ilevel=ensure_ilevel)

	def end_solo(self):
		self._end_solo()

	def _go_solo(self, ensure_ilevel=False, cm=None):

		if not self.solo_enabled:
			raise ExecLockError("Solo mode is disabled => Cannot go solo")

		if cm is None:
			self._solo_last_set = True
			self._solo_cm_map.clear()
		else:
			self._solo_cm_map[cm] = True

		if self._solo_lock.locked:
			return

		new_ilevel = self._current_ilevel()
		if isinstance(ensure_ilevel, bool):
			if ensure_ilevel and new_ilevel < self._solo_ilevel:
				new_ilevel = self._solo_ilevel
		elif new_ilevel < ensure_ilevel:
			new_ilevel = ensure_ilevel
		if new_ilevel < self._solo_ilevel:
			raise ExecLockError(f"Run level needs to be at least {self._level_list[self._solo_ilevel]} ({self._solo_ilevel}) in order to go solo => Wanted to do it at run level {self._level_list[new_ilevel]} ({new_ilevel})")

		self._set_running(False)
		self._set_ilevel(new_ilevel, cm=cm, manage_running=False)

		self._go_solo_cb(True, False)

		with contextlib.ExitStack() as stack:

			self._solo_lock.shared_lock = False
			# noinspection PyTypeChecker
			stack.enter_context(self._solo_lock)
			self._set_running(True, exclusive=True)

			if self.lock_delay > 0:
				time.sleep(self.lock_delay)

			self._go_solo_cb(True, True)

			stack.pop_all()

	def _end_solo(self, cm=None, manage_running=True):

		if cm is None:
			self._solo_last_set = False
			self._solo_cm_map.clear()
		else:
			self._solo_cm_map.pop(cm, None)

		if self._solo_last_set or any(self._solo_cm_map.values()):
			return

		if not self._solo_lock.locked:
			return

		self._go_solo_cb(False, False)

		if manage_running:
			self._set_running(False)
		self._solo_lock.__exit__(None, None, None)

		if cm is not None:
			self._set_ilevel(None, cm=cm, manage_running=manage_running)
		elif manage_running and self._current_ilevel() >= self._running_ilevel:
			self._set_running(True)

		self._go_solo_cb(False, True)

	def _go_solo_cb(self, solo, done):
		pass

	@property
	def solo_pending(self):

		if self._solo_lock.locked or not self.running:
			return False

		return not self._solo_lock.test_lockable(shared_lock=True)

	def yield_to_solo(self):

		if self._solo_lock.locked or not self.running:
			return

		self._yield_solo_cb(False)
		self._set_running(False)
		self._solo_lock.touch_lock(shared_lock=True)
		self._set_running(True)
		self._yield_solo_cb(True)

		time.sleep(self.check_interval)

	def _yield_solo_cb(self, done):
		pass
# EOF
