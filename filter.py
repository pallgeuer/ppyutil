# Filter utilities

# Imports
import math

# First order low pass filter
class LowPassFilter:

	def __init__(self, settling_time, init_value=0, freeze=False):
		# settling_time = Desired 90% settling time of the filter in units of cycles
		# init_value = Initial value of the filtered output
		self.settling_time = settling_time
		self.value = init_value
		self.freeze = freeze

	def reset(self, init_value=0, settling_time=None, freeze=None):
		self.value = init_value
		if settling_time is not None:
			self.settling_time = settling_time
		if freeze is not None:
			self.freeze = freeze

	def filter(self, value):
		if not self.freeze:
			self.value += self._alpha * (value - self.value)
		return self.value

	@property
	def settling_time(self):
		return self._settling_time

	@settling_time.setter
	def settling_time(self, settling_time):
		if settling_time <= 0 or math.isinf(settling_time):
			self._settling_time = 0
			self._alpha = 1
		else:
			self._settling_time = settling_time
			self._alpha = 1 - 0.10 ** (1 / settling_time)

	@property
	def alpha(self):
		return self._alpha

	@classmethod
	def compute_alpha(cls, settling_time, dt):
		return 1 - 0.10 ** (dt / settling_time)
# EOF
