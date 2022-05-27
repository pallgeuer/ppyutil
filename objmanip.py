# Object manipulation utilities

# Imports
import sys
import copy
import datetime
from enum import Enum

# Constants
simple_types = (dict, list, str, float, int, bool, type(None))

# Simplify an object so that it only contains certain predefined simple types (output is a totally independent reworked copy of the object data)
def simplify_object(obj):
	if isinstance(obj, dict):
		return {key: simplify_object(value) for key, value in obj.items() if type(key) in simple_types}
	elif isinstance(obj, list):
		return [simplify_object(value) for value in obj]
	elif type(obj) in simple_types:
		return obj
	elif callable(getattr(obj, 'asdict', None)):
		obj_asdict = obj.asdict()
		if isinstance(obj_asdict, dict):
			return simplify_object(obj_asdict)
	elif callable(getattr(obj, '_asdict', None)):
		# noinspection PyProtectedMember
		obj_asdict = obj._asdict()
		if isinstance(obj_asdict, dict):
			return simplify_object(obj_asdict)
	elif isinstance(obj, tuple):
		return [simplify_object(value) for value in obj]
	elif isinstance(obj, Enum):
		return str(obj.name)
	elif isinstance(obj, datetime.datetime):
		return str(obj)
	else:
		return repr(obj)

# Flatten any nested dicts contained in an object to become single-level dicts (output is a totally independent reworked copy of the object data)
# Note: This is only guaranteed to find nested dicts that are recursible through fundamental data types, and may demote certain classes to their corresponding base fundamental types
def flatten_object_dicts(obj, flatten_all=True):
	if isinstance(obj, dict):
		return flatten_nested_dict(obj, flatten_all=flatten_all)[0]
	elif isinstance(obj, list):
		if flatten_all:
			return flatten_nested_dict(dict(enumerate(obj)), flatten_all=flatten_all)[0]
		else:
			return [flatten_object_dicts(value, flatten_all=flatten_all) for value in obj]
	elif isinstance(obj, tuple):
		if flatten_all:
			return flatten_nested_dict(dict(enumerate(obj)), flatten_all=flatten_all)[0]
		else:
			return tuple(flatten_object_dicts(value, flatten_all=flatten_all) for value in obj)
	else:
		return copy.deepcopy(obj)

# Recursively flatten a nested dictionary (output is a totally independent reworked copy of the object data)
# Note: This function is only intended as a worker function for flatten_object_dicts() => Use this instead unless you explicitly need the duplicate keys output
def flatten_nested_dict(obj, flatten_all=True, out=None, prefix=None, dup_keys=None):

	if out is None:
		out = {}
	if prefix is None:
		prefix = []
	if dup_keys is None:
		dup_keys = []

	for key, value in obj.items():
		prefix.append(str(key))
		if isinstance(value, dict):
			flatten_nested_dict(value, flatten_all=flatten_all, out=out, prefix=prefix, dup_keys=dup_keys)
		elif flatten_all and isinstance(value, (list, tuple)):
			flatten_nested_dict(dict(enumerate(value)), flatten_all=flatten_all, out=out, prefix=prefix, dup_keys=dup_keys)
		else:
			flat_key = '/'.join(prefix)
			if flat_key in out:
				dup_keys.append(flat_key)
			else:
				out[flat_key] = flatten_object_dicts(value, flatten_all=flatten_all)
		prefix.pop()

	return out, dup_keys

# Recursively measure the size in bytes of a Python object
# Source: https://goshippo.com/blog/measure-real-size-any-python-object
def get_size(obj, seen=None):
	size = sys.getsizeof(obj)
	if seen is None:
		seen = set()
	obj_id = id(obj)
	if obj_id in seen:
		return 0
	seen.add(obj_id)
	if isinstance(obj, dict):
		size += sum([get_size(v, seen) for v in obj.values()])
		size += sum([get_size(k, seen) for k in obj.keys()])
	elif hasattr(obj, '__dict__'):
		size += get_size(obj.__dict__, seen)
	elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
		size += sum([get_size(i, seen) for i in obj])
	return size
# EOF
