# Generic module classes for executing tasks optionally in a child process

# Imports
import abc
import time
import queue
import itertools
import contextlib
import multiprocessing
from typing import Any

# Constants
MP = multiprocessing.get_context('forkserver')  # Note: Forkserver (or spawn) is required instead of fork if you want to use CUDA in the subprocesses

# Data signal classes
class DataPending:
	pass
class DataAbort:
	pass

# Element class
class Element(abc.ABC):

	def __init__(self, remote):
		# remote = Whether any link to this element needs to be remote
		self.remote = remote
		self.input_receiver = None
		self.output_senders = []
		self.pipeline = None

	@staticmethod
	def link(src, dest):
		# src = Element to link the output of
		# dest = Element to link the input of
		sender = src.create_sender(remote=src.remote or dest.remote)
		src.output_senders.append(sender)
		dest.input_receiver = sender.create_receiver()

	def create_sender(self, remote):
		# remote = Whether to create a remote sender
		# Return a new sender of the required type
		return self.create_remote_sender() if remote else FieldSender()

	def create_remote_sender(self):
		# Return a new sender of the required type
		return QueueSender()

	def register_pipeline(self, pipeline):
		self.pipeline = pipeline

	@abc.abstractmethod
	def step(self):
		# Return whether the next call to step() will have work to do
		pass

# Sink class
class Sink(Element):

	def __init__(self):
		super().__init__(False)
		self.done = True

	def __enter__(self):
		# Return the class instance
		self.done = False
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# exc_type, exc_val, exc_tb = Details of the exception that occurred (if any)
		# Return whether to suppress the exception
		self.done = True
		return False

	def create_sender(self, remote):
		raise RuntimeError("Sinks cannot create senders")

	def step(self, block=True):
		# block = Whether to block until sink data is available
		# Return the received sink data and whether the next call to step() will have work to do
		sink_data = None
		if not self.done:
			with contextlib.suppress(BlockingIOError):
				sink_data = self.get_data(block=block)
				if sink_data is None:
					self.done = True
		return sink_data, not self.done

	def get_data(self, block=True):
		# block = Whether to block until data is available
		# Return the sink data or raise BlockingIOError if block is False but no data is available
		return self.input_receiver.receive(block=block)

	def process(self, sink_data):
		# sink_data = Sink data to process
		pass

# Module task class
class ModuleTask(abc.ABC):

	# The module task corresponding to a module is the class that actually executes the task, and exists in the subprocess
	# if the module is remote. The task receives data via the input receiver, one object at a time, processes it, and
	# outputs the result to all of its senders. Input is queried and received until a None is received (which is NOT passed
	# on to a call to process() then), at which point the task is complete and no further actions or calls to process()
	# occur. If there is no input receiver configured at all for the task, the process() method will continue to be called
	# with None all the time, until it returns None and the task is complete. If an input receiver is present and process()
	# returns a None of its own accord, no further call to process() occurs, but the task remains active in the sense that
	# it continues to query and receive input data (until an input None is received at least), but doesn't do anything with
	# that data. This is to make sure that parent tasks don't get blocked trying to send data that no-one receives anymore.
	# If process() at any point returns DataPending, all child tasks skip their call to process() and essentially just wait
	# for future data that is not DataPending. If process() at any point returns DataAbort, None is sent to all output
	# senders and the pipeline is put into the aborted state. This is noticed by all other tasks in the pipeline during
	# their next call to step(), and they subsequently all exit.

	def __init__(self, input_receiver, output_senders, abort_event):
		# input_receiver = Receiver to retrieve input data from (may be None)
		# output_senders = Sequence of senders to supply with output data
		# abort_event = Event that can be used to abort the pipeline
		self.input_receiver = input_receiver
		if self.input_receiver:
			self.input_receiver.init()
		self.output_senders = tuple(output_senders)
		for output_sender in self.output_senders:
			output_sender.init()
		self.abort_event = abort_event
		self.input_done = True
		self.output_done = True

	def __enter__(self):
		# Return the class instance
		self.input_done = False
		self.output_done = False
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# exc_type, exc_val, exc_tb = Details of the exception that occurred (if any)
		# Return whether to suppress the exception
		if not (self.input_done and self.output_done):
			self.abort_event.set()
		self.handle_exit()
		return False

	def handle_exit(self):
		if not self.output_done:
			for output_sender in self.output_senders:
				output_sender.send(None)
		self.input_done = True
		self.output_done = True

	def step(self):
		# Return whether the next call to step() will have work to do
		if not (self.input_done and self.output_done):
			if self.abort_event.is_set():
				self.handle_exit()
			else:
				output_data = None
				if not self.input_done:
					input_data = self.input_receiver.receive(block=True) if self.input_receiver else None
					if input_data is None:
						self.input_done = True
					elif input_data == DataPending:
						output_data = DataPending
					elif not self.output_done:
						output_data = self.process(input_data)
				if not self.output_done:
					if not self.input_receiver:
						output_data = self.process(None)
					if output_data == DataAbort:
						self.abort_event.set()
						self.handle_exit()
					elif output_data != DataPending:
						for output_sender in self.output_senders:
							output_sender.send(output_data)
						if output_data is None:
							self.output_done = True
		return not (self.input_done and self.output_done)

	@abc.abstractmethod
	def process(self, input_data) -> Any:
		# input_data = Input data to process
		# Return the processed output data
		pass

# Module class
class Module(Element):

	def __init__(self, remote, *task_args, **task_kwargs):
		# remote = Whether this module should run its task in a subprocess
		# task_args = Extra arguments to supply to the module task
		# task_kwargs = Extra keyword arguments to supply to the module task
		super().__init__(remote)
		self.task_args = task_args
		self.task_kwargs = task_kwargs
		self.task = None
		self.proc = None

	@classmethod
	@abc.abstractmethod
	def create_task(cls, input_receiver, output_senders, abort_event, *task_args, **task_kwargs) -> ModuleTask:
		# input_receiver = Receiver to retrieve input data from
		# output_senders = List of senders to supply with output data
		# abort_event = Event that can be used to abort the pipeline
		# task_args = Extra arguments to supply to the module task
		# task_kwargs = Extra keyword arguments to supply to the module task
		pass

	def __enter__(self):
		# Return the class instance
		if self.remote:
			self.proc = MP.Process(target=self.run, args=(self.input_receiver, self.output_senders, self.pipeline.abort_event, self.task_args, self.task_kwargs), daemon=True)
			self.proc.start()
		else:
			self.task = self.create_task(self.input_receiver, self.output_senders, self.pipeline.abort_event, *self.task_args, **self.task_kwargs)
			self.task.__enter__()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# exc_type, exc_val, exc_tb = Details of the exception that occurred (if any)
		# Return whether to suppress the exception
		if self.remote:
			self.proc.join()
			self.proc = None
		else:
			self.task.__exit__(None, None, None)
			self.task = None
		return False

	def step(self):
		# Return whether the next call to step() will have work to do
		return self.task is not None and self.task.step()

	@classmethod
	def run(cls, input_receiver, output_senders, abort_event, task_args, task_kwargs):
		# input_receiver = Receiver to retrieve input data from
		# output_senders = List of senders to supply with output data
		# abort_event = Event that can be used to abort the pipeline
		# task_args = Extra arguments to supply to the module task
		# task_kwargs = Extra keyword arguments to supply to the module task
		with cls.create_task(input_receiver, output_senders, abort_event, *task_args, **task_kwargs) as task:
			while task.step():
				pass

# Pipeline class
class Pipeline:

	def __init__(self, *modules, wait_time=3):
		# modules = Ordered list of modules and sinks to incorporate into the pipeline
		# wait_time = If no local work needs to be done to run the pipeline and there is not just one sink that can comfortably block, wait this number of ms per cycle to avoid running an empty main loop at 100% CPU
		self.modules = tuple(module for module in modules if not isinstance(module, Sink))
		self.sinks = tuple(module for module in modules if isinstance(module, Sink))
		self.wait_time = wait_time / 1000
		self.abort_event = MP.Event()
		for element in itertools.chain(self.modules, self.sinks):
			element.register_pipeline(self)

	# noinspection PyUnusedLocal
	def _exit_handler(self, exc_type, exc_val, exc_tb):
		if exc_type is not None:
			self.abort_event.set()
		return False

	def run(self):
		zero_sinks = not self.sinks
		single_sink = (len(self.sinks) == 1)
		with contextlib.ExitStack() as stack:
			for i in range(len(self.sinks) - 1, -1, -1):
				stack.enter_context(self.sinks[i])
			for i in range(len(self.modules) - 1, -1, -1):
				stack.enter_context(self.modules[i])
			stack.push(self._exit_handler)
			while not self.abort_event.is_set():
				local_work_ongoing = False
				for module in self.modules:
					local_work_ongoing |= module.step()
				any_sink_ongoing = False
				for sink in self.sinks:
					sink_data, sink_ongoing = sink.step(block=not local_work_ongoing and single_sink)
					if sink_ongoing and sink_data is not None:
						self.process_sink_data(sink, sink_data)
					any_sink_ongoing |= sink_ongoing
				if not local_work_ongoing:
					if not any_sink_ongoing and not zero_sinks:  # If there are no sinks then we cannot know when the pipeline is actually finished, so we just keep going until we receive a kill signal (e.g. SIGINT) or an internal abort
						break
					if not single_sink:
						time.sleep(self.wait_time)

	# noinspection PyMethodMayBeStatic
	def process_sink_data(self, sink, sink_data):
		# sink = Sink module that received data
		# sink_data = Data that was received
		# The default behaviour of forwarding the data procesing to the sink class can be overridden here if desired (if multiple sinks need to share state easily)
		sink.process(sink_data)

# Receiver class
class Receiver(abc.ABC):

	def init(self):
		# Perform initialisation actions that need to occur within the target process that the receiver will operate in
		pass

	@abc.abstractmethod
	def receive(self, block=True) -> Any:
		# block = Whether to block until data is available
		# Return the received data or raise BlockingIOError if block is False but no data is available
		pass

	@abc.abstractmethod
	def new_data(self) -> bool:
		# Return whether new data has become available since the last data that was returned from receive()
		pass

# Sender class
class Sender(abc.ABC):

	def init(self):
		# Perform initialisation actions that need to occur within the target process that the sender will operate in
		pass

	@abc.abstractmethod
	def create_receiver(self) -> Receiver:
		# Return a receiver for the sender (only one should be created for each sender)
		pass

	@abc.abstractmethod
	def send(self, data):
		# data = Data to send
		pass

# Field receiver class
class FieldReceiver(Receiver):

	def __init__(self, sender):
		self.sender = sender

	def receive(self, block=True):
		if self.sender.data_new:
			self.sender.data_new = False
			return self.sender.data
		elif block:
			raise OSError("No new data => Field receiver cannot block and wait for new data")
		else:
			raise BlockingIOError

	def new_data(self):
		return self.sender.data_new

# Field sender class
class FieldSender(Sender):

	def __init__(self):
		self.data = None
		self.data_new = False

	def create_receiver(self):
		return FieldReceiver(self)

	def send(self, data):
		self.data = data
		self.data_new = True

# Queue receiver class
class QueueReceiver(Receiver):

	def __init__(self, sender_queue):
		self.queue = sender_queue

	def receive(self, block=True):
		try:
			data = self.queue.get(block=block)
		except queue.Empty:
			raise BlockingIOError
		return data

	def new_data(self):
		return self.queue.full()

# Queue sender class
class QueueSender(Sender):

	def __init__(self):
		self.queue = MP.Queue(maxsize=1)

	def create_receiver(self):
		return QueueReceiver(self.queue)

	def send(self, data):
		self.queue.put(data, block=True)

# Shared memory receiver class
class SharedMemoryReceiver(Receiver):

	def __init__(self, lock, read_event, write_event):
		self.lock = lock
		self.read_event = read_event
		self.write_event = write_event

	def receive(self, block=True):
		if block:
			self.write_event.wait()
		elif not self.write_event.is_set():
			raise BlockingIOError
		with self.lock:
			data = self.read_data()
			self.write_event.clear()
			self.read_event.set()
		return data

	def new_data(self):
		return self.write_event.is_set()

	@abc.abstractmethod
	def read_data(self):
		# Return the data stored in shared memory (needs to be able to receive None/DataPending)
		pass

# Shared memory sender class
class SharedMemorySender(Sender):

	def __init__(self):
		self.lock = MP.RLock()
		self.read_event = MP.Event()
		self.write_event = MP.Event()
		self.read_event.set()

	@abc.abstractmethod
	def create_receiver(self):
		# Return a shared memory receiver that has access to all the required shared memory variables
		return SharedMemoryReceiver(self.lock, self.read_event, self.write_event)

	def send(self, data):
		self.read_event.wait()
		with self.lock:
			self.write_data(data)
			self.read_event.clear()
			self.write_event.set()

	@abc.abstractmethod
	def write_data(self, data):
		# data = Data to write into shared memory (needs to be able to send None/DataPending)
		pass
# EOF
