# NVIDIA SMI utility interface

# Imports
from pynvml.smi import *

# NVIDIA SMI user class
# noinspection PyPep8Naming
class NvidiaSMI:

	def __init__(self):
		self._impl = _NvidiaSMI.getInstance()

	def __del__(self):
		self._impl = None
		_NvidiaSMI.ungetInstance()

	def DeviceQuery(self, *args, **kwargs):
		return self._impl.DeviceQuery(*args, **kwargs)

	def XmlDeviceQuery(self, *args, **kwargs):
		return self._impl.XmlDeviceQuery(*args, **kwargs)

	def format(self, *args, **kwargs):
		return self._impl.format(*args, **kwargs)

# NVIDIA SMI wrapper metaclass
class _NvidiaSMIMeta(type):

	@property
	def _nvidia_smi__handles(cls):
		# noinspection PyUnresolvedReferences
		return cls._NvidiaSMI__handles

# NVIDIA SMI wrapper class
# noinspection PyPep8Naming
class _NvidiaSMI(metaclass=_NvidiaSMIMeta):

	__instance = None
	__handles = None
	__ref_count = 0

	@staticmethod
	def getInstance():
		if _NvidiaSMI.__instance is None:
			_NvidiaSMI.__ref_count = 1
			_NvidiaSMI()
		elif _NvidiaSMI.__ref_count >= 0:
			_NvidiaSMI.__ref_count += 1
		else:
			_NvidiaSMI.__ref_count = 1
		return _NvidiaSMI.__instance

	@staticmethod
	def ungetInstance():
		_NvidiaSMI.__ref_count -= 1
		if _NvidiaSMI.__ref_count <= 0:
			_NvidiaSMI.__deleteInstance()

	@staticmethod
	def __deleteInstance():
		_NvidiaSMI.__instance = None
		_NvidiaSMI.__ref_count = 0
		_NvidiaSMI.__deinitialise_nvml()

	def __init__(self):
		if _NvidiaSMI.__instance is None and _NvidiaSMI.__ref_count == 1:
			_NvidiaSMI.__instance = self
			_NvidiaSMI.__initialise_nvml()
		else:
			raise Exception("This class should only be instantiated using getInstance()")

	def __del__(self):
		if _NvidiaSMI.__instance is not None and _NvidiaSMI.__instance is self:
			_NvidiaSMI.__deleteInstance()

	@staticmethod
	def __initialise_nvml():
		nvmlInit()
		device_count = nvmlDeviceGetCount()
		_NvidiaSMI.__handles = {}
		for i in range(device_count):
			_NvidiaSMI.__handles[i] = nvmlDeviceGetHandleByIndex(i)

	@staticmethod
	def __deinitialise_nvml():
		_NvidiaSMI.__handles = None
		nvmlShutdown()

	def DeviceQuery(self, *args, **kwargs):
		# noinspection PyUnresolvedReferences
		return nvidia_smi.DeviceQuery.__func__(self.__class__, *args, **kwargs)
# EOF
