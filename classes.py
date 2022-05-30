# Class utilities

# Imports
import enum
import collections

#
# Method decorators
#

# Class property
# noinspection PyPep8Naming
class classproperty(property):
	# Note: __set__() does not get called when setting an attribute of a class, so this does not intercept or protect against class-level writes to the property

	def __init__(self, fget=None, doc=None):
		super().__init__(fget=fget, fset=None, fdel=None, doc=doc)

	def __get__(self, obj, objtype=None):
		if objtype is None:
			objtype = type(obj)
		if self.fget is None:
			raise AttributeError("unreadable class attribute")
		# noinspection PyArgumentList
		return self.fget(objtype)

# Static property
# noinspection PyPep8Naming
class staticproperty(property):
	# Note: __set__() does not get called when setting an attribute of a class, so this does not intercept or protect against class-level writes to the property

	def __init__(self, fget=None, doc=None):
		super().__init__(fget=fget, fset=None, fdel=None, doc=doc)

	def __get__(self, obj, objtype=None):
		if self.fget is None:
			raise AttributeError("unreadable static attribute")
		# noinspection PyArgumentList
		return self.fget()

# Function decorator that inserts the decorated function as an instance method of an existing class, optionally changing the function's name in the process
# This can be useful, for example, if you are using metaclasses to add methods to a class and want them to appear as if they had been defined normally inside the class body
# noinspection PyPep8Naming
class instance_method_of:

	def __init__(self, cls, name=None, mangle=False):
		self.cls = cls
		self.name = name
		self.mangle = mangle

	def __call__(self, func):
		if self.name is not None:
			func.__name__ = self.name
		func.__qualname__ = f'{self.cls.__qualname__}.{func.__name__}'
		func.__module__ = self.cls.__module__
		setattr(self.cls, mangle_attr(self.cls, func.__name__) if self.mangle else func.__name__, func)
		return func

#
# Extended standard classes
#

# For default arguments that may be None
_NONE = object()

# Ordered enumeration
class OrderedEnum(enum.Enum):

	def __ge__(self, other):
		if self.__class__ is other.__class__:
			return self.value >= other.value
		return NotImplemented

	def __gt__(self, other):
		if self.__class__ is other.__class__:
			return self.value > other.value
		return NotImplemented

	def __le__(self, other):
		if self.__class__ is other.__class__:
			return self.value <= other.value
		return NotImplemented

	def __lt__(self, other):
		if self.__class__ is other.__class__:
			return self.value < other.value
		return NotImplemented

# Enumeration with support for case-insensitive string lookup (case sensitive string lookup is already available by default)
# Note: If we have "class MyEnum(Enum): One = 1" then MyEnum(1) = MyEnum['One'] = MyEnum.One
class EnumLU(enum.Enum):

	@classmethod
	def from_str(cls, string, default=_NONE):
		string = string.lower()
		for name, enumval in cls.__members__.items():
			if string == name.lower():
				return enumval
		if default is _NONE:
			raise LookupError(f"Failed to convert case insensitive string to enum type {cls.__name__}: '{string}'")
		else:
			return default

	@classmethod
	def has_str(cls, string):
		string = string.lower()
		for name in cls.__members__:
			if string == name.lower():
				return True
		return False

# Ordered EnumLU enumeration
class OrderedEnumLU(OrderedEnum, EnumLU):
	pass

# Enumeration that uses the first argument as its value
class EnumFI(enum.Enum):

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls._values = []

	# noinspection PyProtectedMember, PyArgumentList, PyUnresolvedReferences
	def __new__(cls, *args, **kwargs):
		value = args[0]
		if isinstance(value, enum.auto):
			if value.value == enum._auto_null:
				# noinspection PyTypeChecker
				value.value = cls._generate_next_value_(None, 1, len(cls.__members__), cls._values[:])  # Note: This just passes None for the key, which is generally okay
			value = value.value
			args = (value,) + args[1:]
		cls._values.append(value)
		instance = cls._member_type_.__new__(cls, *args, **kwargs)
		instance._value_ = value
		return instance

	def __format__(self, format_spec):
		return str.__format__(str(self), format_spec)

# Function to create a namedtuple type with default values (Python 3.7+ makes this obsolete by adding the defaults keyword to namedtuple, and by introducing dataclasses)
# The argument 'default_values' can be omitted (meaning all 'default_value' by default), can be a list (e.g. [1, 2, 3]) or a dict (e.g. {'argb': 7})
# Source: https://stackoverflow.com/questions/11351032/namedtuple-and-default-values-for-optional-keyword-arguments
# noinspection PyUnresolvedReferences, PyProtectedMember, PyArgumentList
def namedtuple_with_defaults(typename, field_names, default_values=(), default_value=None):
	T = collections.namedtuple(typename, field_names)
	T.__new__.__defaults__ = (default_value,) * len(T._fields)
	if isinstance(default_values, collections.Mapping):
		prototype = T(**default_values)
	else:
		prototype = T(*default_values)
	T.__new__.__defaults__ = tuple(prototype)
	return T

#
# Helper functions
#

# Function that evaluates the result of name mangling on an attribute (leaves all non-private attributes untouched)
def mangle_attr(cls, attr):
	mangle_code = "class {cls}:\n\t@staticmethod\n\tdef mangle():\n\t\t{attr} = None"
	if not isinstance(cls, str):
		cls = cls.__name__
	result = {}
	eval(compile(mangle_code.format(cls=cls, attr=attr), '', 'exec'), {}, result)
	return result[cls].mangle.__code__.co_varnames[0]
# EOF
