# Filter utilities

# Imports
import math

# First order low pass filter
class LowPassFilter:

	def __init__(self, Ts, init_value=0, freeze=False):
		# Ts = Desired 90% settling time of the filter in units of cycles
		# init_value = Initial value of the filtered output
		self.Ts = Ts
		self.value = init_value
		self.freeze = freeze

	def reset(self, init_value=0, Ts=None, freeze=None):
		self.value = init_value
		if Ts is not None:
			self.Ts = Ts
		if freeze is not None:
			self.freeze = freeze

	def filter(self, value):
		if not self.freeze:
			self.value += self._alpha * (value - self.value)
		return self.value

	@property
	def Ts(self):
		return self._Ts

	@Ts.setter
	def Ts(self, Ts):
		if Ts <= 0 or math.isinf(Ts):
			self._Ts = 0
			self._alpha = 1
		else:
			self._Ts = Ts
			self._alpha = 1 - 0.10 ** (1 / Ts)

	@property
	def alpha(self):
		return self._alpha

	@classmethod
	def computeAlpha(cls, Ts, dT):
		return 1 - 0.10 ** (dT / Ts)
# EOF
