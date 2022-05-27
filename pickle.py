# Pickle utilities

# Imports
import io
import sys
import pickle
import inspect
import os.path

# Check whether a type is a built-in class
def is_builtin_class(obj_type):
	return inspect.isclass(obj_type) and not (hasattr(obj_type, '__module__') and hasattr(sys.modules.get(obj_type.__module__), '__file__'))

# Check whether a type is a built-in module
def is_builtin_module(obj_type):
	return inspect.ismodule(obj_type) and not hasattr(obj_type, '__file__')

# Check whether a type is a built-in
def is_builtin(obj_type):
	return is_builtin_class(obj_type) or is_builtin_module(obj_type)

# I/O file class that simply throws away whatever is written to it
class NullFile(io.IOBase):

	def __init__(self):
		pass

	def write(self, *args, **kwargs):
		pass

# Custom pickler that by default throws away the pickled output and just records which types are required for the pickle
class PickleTypeExtractor(pickle.Pickler):

	def __init__(self, builtins=True, **kwargs):
		kwargs.setdefault('file', NullFile())
		super().__init__(**kwargs)
		self.reqd_types = set()
		self.builtins = builtins

	def dump(self, *args, **kwargs):
		self.reqd_types = set()
		super().dump(*args, **kwargs)

	def persistent_id(self, obj):
		obj_type = obj if isinstance(obj, type) else type(obj)
		if self.builtins or not is_builtin(obj_type):
			self.reqd_types.add(obj_type)
		return None

# Wrapper function for applying the PickleTypeExtractor class to a single object (returns a set of types)
def get_pickle_types(obj, builtins=True, **kwargs):
	pickler = PickleTypeExtractor(builtins=builtins, **kwargs)
	pickler.dump(obj)
	return pickler.reqd_types

# Get the source code information of a type
def get_source_code_info(obj_type):
	# obj_type = Any python type (NOT an instance of that type)
	# Return Tuple(obj_type, builtin, filepath, lineno, source) where lineno/source may individually be 0/empty (due to failure or e.g. namedtuples)

	if is_builtin_class(obj_type):
		return obj_type, True, 'Built-in class', 0, ''
	if is_builtin_module(obj_type):
		return obj_type, True, 'Built-in module', 0, ''

	try:
		filepath = inspect.getsourcefile(obj_type)
	except OSError:
		raise OSError(f"Failed to get source file for type: {obj_type}")

	try:
		sourcelines, file_lineno = inspect.getsourcelines(obj_type)
	except OSError:
		if hasattr(obj_type, '_source'):
			# noinspection PyProtectedMember
			sourcelines = [obj_type._source.strip('\n') + '\n']  # Note: Namedtuples have dynamically defined source code
		else:
			sourcelines = []  # Note: Access to the original .py source file is required => The module defining the type does not need to be actually imported, just importable from a .py (not .pyc / .ipynb) file
		file_lineno = 0

	return obj_type, False, filepath, file_lineno, ''.join(sourcelines)

# Get a python code representation from the given source code info (i.e. from a tuple returned from the get_source_code_info() function)
def source_code_from_info(info_tuple):
	if info_tuple[1]:
		return f"# Type: {info_tuple[0]}\n# Source: {info_tuple[2]}\n"
	elif info_tuple[4]:
		return f"# Type: {info_tuple[0]}\n# Source: {info_tuple[2]}:{info_tuple[3]}\n{info_tuple[4]}"
	else:
		return f"# Type: {info_tuple[0]}\n# Source: {info_tuple[2]}\n# Warn: Source code lines not found in source file\n"

# Get the source code of a type
def get_source_code(obj_type):
	return source_code_from_info(get_source_code_info(obj_type))

# Get the complete source code of the types required to pickle a particular object
def get_pickle_types_source_code(obj, include_builtins=False, include_in_prefix=False, **kwargs):
	# obj = Object to get the complete source code for
	# include_builtins = Include built-in types
	# include_in_prefix = Include source code installed in the python prefix
	# kwargs = Keyword arguments passed to internal PickleTypeExtractor
	# Return required complete source code as a string
	reqd_types = get_pickle_types(obj, **kwargs)
	source_infos = []
	for reqd_type in reqd_types:
		source_info = get_source_code_info(reqd_type)
		if source_info[1]:
			if not include_builtins:
				continue
		elif not include_in_prefix and (os.path.commonpath([sys.base_prefix]) == os.path.commonpath([sys.base_prefix, source_info[2]]) or os.path.commonpath([sys.prefix]) == os.path.commonpath([sys.prefix, source_info[2]])):
			continue
		source_infos.append(source_info)
	source_infos.sort(key=lambda info: (not info[1], info[2], info[3], info[4], getattr(info[0], '__name__', '')))
	return '\n'.join(source_code_from_info(source_info) for source_info in source_infos)
# EOF
