# Generic module classes for executing tasks optionally in a child process

# Imports
import abc
import queue
import contextlib
import multiprocessing
from typing import Any

# Global constants
MP = multiprocessing.get_context('spawn')
DATA_PENDING = object()

# Element class
class Element(abc.ABC):

	def __init__(self, remote):
		# remote = Whether any link to this element needs to be remote
		self.remote = remote
		self.input_receiver = None
		self.output_senders = []

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
		raise NotImplementedError

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

# Module task class
class ModuleTask(abc.ABC):

	def __init__(self, input_receiver, output_senders):
		# input_receiver = Receiver to retrieve input data from
		# output_senders = List of senders to supply with output data
		self.input_receiver = input_receiver
		self.output_senders = output_senders
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
		self.input_done = True
		self.output_done = True
		if exc_type is not None:
			for output_sender in self.output_senders:
				output_sender.send(None)
		return False

	def step(self):
		# Return whether the next call to step() will have work to do
		if not (self.input_done and self.output_done) and (not self.input_receiver or self.input_receiver.new_data()):
			output_data = None
			if not self.input_done:
				input_data = self.input_receiver.receive() if self.input_receiver else None
				if input_data is None:
					self.input_done = True
				elif not self.output_done:
					output_data = self.process(input_data)
			if not self.output_done:
				if not self.input_receiver:
					output_data = self.process(None)
				if output_data != DATA_PENDING:
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
	def create_task(cls, input_receiver, output_senders, *task_args, **task_kwargs) -> ModuleTask:
		# input_receiver = Receiver to retrieve input data from
		# output_senders = List of senders to supply with output data
		# task_args = Extra arguments to supply to the module task
		# task_kwargs = Extra keyword arguments to supply to the module task
		pass

	def __enter__(self):
		# Return the class instance
		if self.remote:
			self.proc = MP.Process(target=self.run, args=(self.input_receiver, self.output_senders, self.task_args, self.task_kwargs), daemon=True)
			self.proc.start()
		else:
			self.task = self.create_task(self.input_receiver, self.output_senders, *self.task_args, **self.task_kwargs)
			self.task.__enter__()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# exc_type, exc_val, exc_tb = Details of the exception that occurred (if any)
		# Return whether to suppress the exception
		if self.remote:
			if exc_type is not None:
				self.proc.terminate()
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
	def run(cls, input_receiver, output_senders, task_args, task_kwargs):
		# input_receiver = Receiver to retrieve input data from
		# output_senders = List of senders to supply with output data
		# task_args = Extra arguments to supply to the module task
		# task_kwargs = Extra keyword arguments to supply to the module task
		with cls.create_task(input_receiver, output_senders, *task_args, **task_kwargs) as task:
			while task.step():
				pass

# Receiver class
class Receiver(abc.ABC):

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
		# Return the data stored in shared memory (needs to be able to receive None)
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
		# data = Data to write into shared memory (needs to be able to send None)
		pass
# EOF
