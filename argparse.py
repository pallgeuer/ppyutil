# Argument parsing utilities

# Imports
import copy
import argparse

# Custom argparse type representing a bounded int
class IntRange:

	def __init__(self, imin=None, imax=None):
		self.imin = imin
		self.imax = imax

	def __call__(self, arg):
		try:
			value = int(arg)
		except ValueError:
			raise self.exception()
		if (self.imin is not None and value < self.imin) or (self.imax is not None and value > self.imax):
			raise self.exception()
		return value

	def exception(self):
		if self.imin is not None and self.imax is not None:
			return argparse.ArgumentTypeError(f"Must be an integer in the range [{self.imin}, {self.imax}]")
		elif self.imin is not None:
			return argparse.ArgumentTypeError(f"Must be an integer >= {self.imin}")
		elif self.imax is not None:
			return argparse.ArgumentTypeError(f"Must be an integer <= {self.imax}")
		else:
			return argparse.ArgumentTypeError("Must be an integer")

# Custom argparse type representing a bounded float
class FloatRange:

	def __init__(self, imin=None, imax=None):
		self.imin = imin
		self.imax = imax

	def __call__(self, arg):
		try:
			value = float(arg)
		except ValueError:
			raise self.exception()
		if (self.imin is not None and value < self.imin) or (self.imax is not None and value > self.imax):
			raise self.exception()
		return value

	def exception(self):
		if self.imin is not None and self.imax is not None:
			return argparse.ArgumentTypeError(f"Must be an float in the range [{self.imin}, {self.imax}]")
		elif self.imin is not None:
			return argparse.ArgumentTypeError(f"Must be a float >= {self.imin}")
		elif self.imax is not None:
			return argparse.ArgumentTypeError(f"Must be a float <= {self.imax}")
		else:
			return argparse.ArgumentTypeError("Must be an float")

# Custom argparse action to append data to a list as tuples
class AppendData(argparse.Action):

	# noinspection PyShadowingBuiltins
	def __init__(self, option_strings, dest, key, nargs=0, const=None, default=None, type=None, required=False, help=None, metavar=None):
		super(AppendData, self).__init__(option_strings=option_strings, dest=dest, nargs=nargs, const=const, default=default, type=type, required=required, help=help, metavar=metavar)
		self.key = key

	def __call__(self, parser, namespace, values, option_string=None):
		if getattr(namespace, self.dest, None) is None:
			setattr(namespace, self.dest, [])
		items = copy.copy(getattr(namespace, self.dest))
		if not values:
			items.append((self.key, None))
		else:
			items.append((self.key, values))
		setattr(namespace, self.dest, items)
# EOF
