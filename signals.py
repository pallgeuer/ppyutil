# Signal utilities

# Imports
import os
import signal

# Context manager for defering signals until the end of a block of code
# Adapted from: David Evans (2013), MIT License, https://gist.github.com/evansd/2375136
class DeferSignals:
	"""
	Context manager to defer signal handling until context exits.

	Takes optional list of signals to defer (default: SIGHUP, SIGINT, SIGTERM).
	Signals can be identified by number or by name.

	Allows you to wrap instruction sequences that ought to be atomic and ensure
	that they don't get interrupted mid-way.
	"""

	def __init__(self, signal_list=None):
		# Default list of signals to defer
		if signal_list is None:
			signal_list = [signal.SIGHUP, signal.SIGINT, signal.SIGTERM]
		# Accept either signal numbers or string identifiers
		self.signal_list = [getattr(signal, sig_id) if isinstance(sig_id, str) else sig_id for sig_id in signal_list]
		self.deferred = []
		self.previous_handlers = {}

	# noinspection PyUnusedLocal
	def defer_signal(self, sig_num, stack_frame):
		# Temporary signal handler just records which signals occurred
		self.deferred.append(sig_num)

	def __enter__(self):
		# Replace existing handlers with deferred handler
		for sig_num in self.signal_list:
			# signal.signal returns None when no handler has been set in Python,
			# which is the same as the default handler (SIG_DFL) being set
			self.previous_handlers[sig_num] = (signal.signal(sig_num, self.defer_signal) or signal.SIG_DFL)
		return self

	def __exit__(self, *args):
		# Restore handlers
		for sig_num, handler in self.previous_handlers.items():
			signal.signal(sig_num, handler)
		# Send deferred signals
		while self.deferred:
			sig_num = self.deferred.pop(0)
			os.kill(os.getpid(), sig_num)

	def __call__(self):
		"""
		If there are any deferred signals pending, trigger them now

		This means that instead of this code:

			for item in collection:
				with defer_signals():
					item.process()

		You can write this:

			with defer_signals() as handle_signals:
				for item in collection:
					item.process()
					handle_signals()

		Which has the same effect but avoids having to embed the context
		manager in the loop
		"""
		if self.deferred:
			# Reattach the signal handlers and fire signals
			self.__exit__()
			# Put our deferred signal handlers back in place
			self.__enter__()
# EOF
