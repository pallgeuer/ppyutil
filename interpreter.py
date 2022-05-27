# Interpreter utilities

# Imports
import sys

# Determine whether running in a Jupyter notebook (to some probability)
def is_notebook():
	try:
		# noinspection PyUnresolvedReferences
		shell = get_ipython().__class__.__name__
		if shell == 'ZMQInteractiveShell':
			return True   # Jupyter notebook or qtconsole
		elif shell == 'TerminalInteractiveShell':
			return False  # Terminal running IPython
		else:
			return False  # Other type
	except NameError:
		return False      # Probably standard Python interpreter

# Determine whether there is a debugger attached (more precisely, any debugger, profiler, code coverage tool, etc that implements sys.gettrace())
# Examples of False: Run in PyCharm, run script from console, run normal code in Jupyter notebook
# Examples of True: Debug in PyCharm, interactive Python console, explicitly debug code in Jupyter notebook
def debugger_attached():
	return sys.gettrace() is not None
# EOF
