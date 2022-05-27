# Context management utilities

# Imports
import sys
import functools
import itertools
import contextlib
import collections
import dataclasses
from typing import Any, Optional, Callable, Iterable
from util.classes import instance_method_of

# Dynamic context error class
class DynamicContextError(Exception):
	pass

# Dynamic exit node class
@dataclasses.dataclass(eq=False, frozen=True)
class DynamicExitNode:
	key: Any
	obj: Any
	result: Any

# Internal dynamic exit node class
@dataclasses.dataclass(eq=False)
class _DynamicExitNode:
	node: DynamicExitNode
	callback: Callable
	parent: Optional['_DynamicExitNode']

# Dynamic context class (modified ExitStack that allows arbitrary entering and leaving of contexts/callbacks using a nested tree of callbacks)
class DynamicContext(contextlib.AbstractContextManager):
	# Every exit callback (referred to as an 'exit node') that is added to the dynamic context (i.e. by explicitly entering a context,
	# adding an exit function, or adding an arbitrary callback to the dynamic context) is guaranteed to be called prior to leaving the
	# with-block that governs the dynamic context (to the same extent that ExitStack 'guarantees' it). In the absence of any contraints
	# imposed by nesting, the exit callbacks are called in a LIFO manner, just as with ExitStack. If a newly added exit node specifies
	# an existing exit node of the dynamic context as its parent, its 'context' will be nested inside that of the parent. This means
	# that it is guaranteed that the exit callback of the newly added exit node will be called prior to the exit callback of the parent.
	# This is relevant if an exit node is explicitly requested to exit prior to termination of the dynamic context. In this case, all
	# child nodes are recursively exited first, before the node itself is exited and removed from the dynamic context. Note that exit
	# nodes by default do not nest inside the previously added node, and as such can be used to construct overlapping contexts, if
	# required, for example to manage multiple independent resources inside a single with-block. Exit nodes can also be added in
	# subfunctions called from within the with-block, as all it requires is a reference to the DynamicContext object that the with-block
	# was entered with.

	def __init__(self):
		self._exit_nodes = collections.deque()

	def __enter__(self):
		# Return the dynamic context instance
		return self

	def enter_context(self, context, key=None, parent=None):
		# context = Context manager to enter as part of this dynamic context
		# key = Unique hashable key to associate the newly created exit node with (optional)
		# parent = Existing exit node to nest the newly created exit node inside
		# Return the newly created exit node

		cm_type = type(context)
		enter_method = cm_type.__enter__
		exit_method = cm_type.__exit__

		self._check_key(key)
		parent = self._resolve_parent(parent)

		def wrapped_exit_method(exc_type, exc_value, traceback):
			return exit_method(context, exc_type, exc_value, traceback)
		wrapped_exit_method.__self__ = context

		result = enter_method(context)

		node = DynamicExitNode(key=key, obj=context, result=result)
		enode = _DynamicExitNode(node=node, callback=wrapped_exit_method, parent=parent)
		self._exit_nodes.append(enode)

		return node

	def leave_context(self, node):
		# node = Context node to close
		self.close_node(node)

	def register_exit_func(self, exit_func, key=None, parent=None):
		# exit_func = Exit function to register as part of this dynamic context (any callable with the standard __exit__ method signature)
		# key = Unique hashable key to associate the newly created exit node with (optional)
		# parent = Existing exit node to nest the newly created exit node inside
		# Return the newly created exit node

		self._check_key(key)
		parent = self._resolve_parent(parent)

		node = DynamicExitNode(key=key, obj=None, result=None)
		enode = _DynamicExitNode(node=node, callback=exit_func, parent=parent)
		self._exit_nodes.append(enode)

		return node

	def close_exit_func(self, node):
		# node = Exit function node to close
		self.close_node(node)

	def register_callback(self, callback, *cb_args, key=None, parent=None, **cb_kwargs):
		# callback, cb_args, cb_kwargs = Callback (with arguments) to register as part of this dynamic context
		# key = Unique hashable key to associate the newly created exit node with (optional)
		# parent = Existing exit node to nest the newly created exit node inside
		# Return the newly created exit node

		# noinspection PyUnusedLocal
		def wrapped_callback(exc_type, exc_value, traceback):
			callback(*cb_args, **cb_kwargs)
		wrapped_callback.__wrapped__ = callback

		return self.register_exit_func(wrapped_callback, key=key, parent=parent)

	def close_callback(self, node):
		# node = Callback node to close
		self.close_node(node)

	def is_active_node(self, node):
		# node = Exit node to check for
		# Return whether the exit node exists (is active) in this dynamic context
		if isinstance(node, DynamicExitNode):
			return any(n.node is node for n in self._exit_nodes)
		else:
			return self.__contains__(node)

	def is_active_context(self, context):
		if context is None:
			return False
		else:
			return any(n.node.obj is context for n in self._exit_nodes)

	def pop_node(self, node):
		# node = Exit node to pop from the dynamic context and return the callback of without actually calling it (child nodes remain inside the dynamic context and have their grandparent become their parent)
		# Return the exit callback of the node (callable with the standard __exit__ method signature)
		index, enode = self._resolve_node(node)
		for n in itertools.islice(self._exit_nodes, index + 1, None):
			if n.parent is enode:
				n.parent = enode.parent
		del self._exit_nodes[index]
		return enode.callback

	def pop_nodes(self, *nodes, children=True):
		# nodes = Exit nodes (or iterables thereof) to move into a new dynamic context instance (no exit callbacks are called => this is ultimately the responsibility of the new dynamic context)
		# children = Whether to move all recursive children of the specified nodes as well
		# Return the new dynamic context instance containing the moved exit nodes

		new_dynamic_context = type(self)()

		node_set = self._collate_nodes(*nodes)
		index_enode_set, index_enode_list = self._collect_enodes(node_set, children=children)

		if not children:
			enode_map = {}
			for index_enode in enumerate(self._exit_nodes):
				parent_enode = index_enode[1].parent
				parent_index_enode = next((en for en in enumerate(self._exit_nodes) if en[1] is parent_enode), None)
				if parent_index_enode is None:
					if parent_enode is not None:
						index_enode[1].parent = None
					enode_map[index_enode] = None
				elif (index_enode in index_enode_set) == (parent_index_enode in index_enode_set):
					enode_map[index_enode] = enode_map[parent_index_enode]
				else:
					enode_map[index_enode] = parent_index_enode[1]
					index_enode[1].parent = enode_map[parent_index_enode]

		while index_enode_list:
			index, enode = index_enode_list.pop()
			new_dynamic_context._exit_nodes.appendleft(enode)
			del self._exit_nodes[index]

		return new_dynamic_context

	def pop_all(self):
		# Return a new dynamic context instance with all exit nodes from this dynamic context moved into it (no exit callbacks are called => this is ultimately the responsibility of the new dynamic context)
		new_dynamic_context = type(self)()
		new_dynamic_context._exit_nodes = self._exit_nodes
		self._exit_nodes = collections.deque()
		return new_dynamic_context

	def close_node(self, node):
		# node = Exit node to close after closing all of its recursive children (calls the associated exit callbacks)
		index_enode_set, index_enode_list = self._collect_enodes({node}, children=True)
		self._close_enodes(index_enode_list, None, None, None)

	def close_nodes(self, *nodes):
		# nodes = Exit nodes (or iterables thereof) to close after closing all of their recursive children (calls the associated exit callbacks)
		node_set = self._collate_nodes(*nodes)
		index_enode_set, index_enode_list = self._collect_enodes(node_set, children=True)
		self._close_enodes(index_enode_list, None, None, None)

	def close_all(self):
		self._close_enodes(list(enumerate(self._exit_nodes)), None, None, None)

	def __exit__(self, exc_type, exc_value, traceback):
		# exc_type, exc_value, traceback = Details of the exception (if any) that triggered the call to __exit__
		# Return whether to suppress the passed exception instead of reraising it again after __exit__ completion
		return self._close_enodes(list(enumerate(self._exit_nodes)), exc_type, exc_value, traceback)

	def __contains__(self, key):
		# key = Key to check for in the dynamic context
		# Return whether the key exists (is active) in the dynamic context
		return key is not None and any(n.node.key == key for n in self._exit_nodes)

	def __getitem__(self, key):
		# key = Key to get the exit node for
		# Return the exit node that corresponds to the given key (else KeyError)
		if key is None:
			raise KeyError(key)
		node = next((n.node for n in self._exit_nodes if n.node.key == key), None)
		if node is None:
			raise KeyError(key)
		return node

	def __delitem__(self, key):
		# key = Key to close the exit node of
		if key is None:
			raise KeyError(key)
		node = next((n.node for n in self._exit_nodes if n.node.key == key), None)
		if node is None:
			raise KeyError(key)
		self.close_node(node)

	def get(self, key, default=None):
		# key = Key to get the exit node for
		# default = Value to return instead if the key does not exist in the dynamic context
		# Return the exit node that corresponds to the given key
		if key is None:
			return default
		node = next((n.node for n in self._exit_nodes if n.node.key == key), None)
		if node is None:
			return default
		return node

	def keys(self):
		# Return a generator for all keys in the dynamic context
		return (n.node.key for n in self._exit_nodes if n.node.key is not None)

	def key_items(self):
		# Return a generator for all key/node items in the dynamic context
		return ((n.node.key, n.node) for n in self._exit_nodes if n.node.key is not None)

	def key_dict(self):
		# Return a dict of all keys and their corresponding exit nodes
		return {n.node.key: n.node for n in self._exit_nodes if n.node.key is not None}

	def _check_key(self, key):
		try:
			hash(key)
		except TypeError:
			raise DynamicContextError(f"Key is not hashable: {key}") from None
		if self.__contains__(key):
			raise DynamicContextError(f"Key already exists in dynamic context: {key}")

	def _resolve_node(self, node):
		if node is None:
			index_enode = None
		elif isinstance(node, DynamicExitNode):
			index_enode = next((en for en in enumerate(self._exit_nodes) if en[1].node is node), None)
		else:
			index_enode = next((en for en in enumerate(self._exit_nodes) if en[1].node.key == node), None)
		if index_enode is None:
			raise DynamicContextError(f"Specified node could not be resolved in this dynamic context: {node}")
		return index_enode

	def _resolve_parent(self, parent):
		if parent is None:
			return None
		elif isinstance(parent, DynamicExitNode):
			enode = next((n for n in self._exit_nodes if n.node is parent), None)
		else:
			enode = next((n for n in self._exit_nodes if n.node.key == parent), None)
		if enode is None:
			raise DynamicContextError(f"Specified parent node could not be resolved in this dynamic context: {parent}")
		return enode

	@staticmethod
	def _collate_nodes(*nodes):
		node_set = set()
		for node in nodes:
			if isinstance(node, Iterable):
				node_set.update(node)
			else:
				node_set.add(node)
		return node_set

	def _collect_enodes(self, node_set, children):
		index_enode_set = {self._resolve_node(node) for node in node_set}
		index_enode_list = []
		for index_enode in enumerate(self._exit_nodes):
			if index_enode in index_enode_set:
				index_enode_list.append(index_enode)
			elif children:
				parent_enode = index_enode[1].parent
				if any(en[1] is parent_enode for en in index_enode_set):
					index_enode_set.add(index_enode)
					index_enode_list.append(index_enode)
		return index_enode_set, index_enode_list

	def _close_enodes(self, index_enode_list, exc_type, exc_value, traceback):

		received_exc = exc_type is not None
		exc_details: Any = (exc_type, exc_value, traceback)
		frame_exc = sys.exc_info()[1]

		def _fix_exception_context(new_exc, old_exc):
			while True:
				exc_context = new_exc.__context__
				if exc_context is old_exc:
					return
				if exc_context is None or exc_context is frame_exc:
					break
				new_exc = exc_context
			new_exc.__context__ = old_exc

		suppressed_exc = False
		pending_raise = False

		while index_enode_list:
			index, enode = index_enode_list.pop()
			del self._exit_nodes[index]
			cb = enode.callback
			try:
				if cb(*exc_details):
					suppressed_exc = True
					pending_raise = False
					exc_details = (None, None, None)
			except:
				new_exc_details = sys.exc_info()
				_fix_exception_context(new_exc_details[1], exc_details[1])
				pending_raise = True
				exc_details = new_exc_details

		if pending_raise:
			fixed_ctx = None
			try:
				fixed_ctx = exc_details[1].__context__
				raise exc_details[1]
			except BaseException:
				exc_details[1].__context__ = fixed_ctx
				raise

		return received_exc and suppressed_exc

# Generic context manager wrapper that delays the construction of another context manager until __enter__ is called (e.g. useful for open())
class ConstructOnEnter:

	def __init__(self, context_type, *args, **kwargs):
		# context_type = Type of context manager to construct on enter
		# args, kwargs = Arguments to call context_type with
		def construct_context_manager():
			return context_type(*args, **kwargs)
		self._cm_factory = construct_context_manager
		self.cm = None

	def wrapped_context(self):
		if callable(getattr(self.cm, 'wrapped_context', None)):
			return self.cm.wrapped_context()
		else:
			return self.cm

	def __enter__(self):
		self.cm = self._cm_factory()
		return self.cm.__enter__()

	def __exit__(self, exc_type, exc_val, exc_tb):
		suppress = self.cm.__exit__(exc_type, exc_val, exc_tb)
		self.cm = None
		return suppress

# Generic context manager that wraps a context manager instance to make it reentrant
class MakeReentrant:

	def __init__(self, context):
		# context = Context manager to make reentrant by wrapping it
		self.cm = context
		self.result = None
		self._enter_count = 0

	def wrapped_context(self):
		if callable(getattr(self.cm, 'wrapped_context', None)):
			return self.cm.wrapped_context()
		else:
			return self.cm

	def __enter__(self):
		self._enter_count += 1
		if self._enter_count == 1:
			self.result = self.cm.__enter__()
		return self.result

	def __exit__(self, exc_type, exc_val, exc_tb):
		if self._enter_count < 1:
			raise AssertionError("Reentrant context manager should not be exited more times than it is entered")
		elif self._enter_count == 1:
			suppress = self.cm.__exit__(exc_type, exc_val, exc_tb)
			self.result = None
		else:
			suppress = False
		self._enter_count -= 1
		return suppress

# Base class to allow easy definition of reentrant context managers
class ReentrantBase:
	# Simply insert ReentrantBase as the first base class, and if required define _enter() and _exit() methods to customise the enter/exit handling.
	# The __enter__ and __exit__ methods from ReentrantBase should no longer be overridden unless you know exactly what you're doing and have a very good reason to do so.
	# Although super calls to __enter__ and __exit__ INSIDE _enter/_exit are redirected to the base classes following ReentrantBase in the MRO, beware that this only works
	# if the call to _enter/_exit originated from the ReentrantBase __enter__/__exit__ methods.
	# If CMClass is any non-reentrant context manager, the simplest application of ReentrantBase simply involves doing "class ReentrantCMClass(ReentrantBase, CMClass): pass".

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._enter_count = 0
		self._enter_result = None
		self._entering = False
		self._exiting = False

	def __enter__(self):
		if self._entering or self._exiting:
			# noinspection PyUnresolvedReferences
			return super().__enter__()
		try:
			self._entering = True
			self._enter_count += 1
			if self._enter_count == 1:
				self._enter_result = self._enter()
		finally:
			self._entering = False
		return self._enter_result

	def __exit__(self, exc_type, exc_val, exc_tb):
		if self._entering or self._exiting:
			# noinspection PyUnresolvedReferences
			return super().__exit__(exc_type, exc_val, exc_tb)
		try:
			self._exiting = True
			if self._enter_count < 1:
				raise AssertionError("Reentrant context manager should not be exited more times than it is entered")
			elif self._enter_count == 1:
				suppress = self._exit(exc_type, exc_val, exc_tb)
				self._enter_result = None
			else:
				suppress = False
			self._enter_count -= 1
		finally:
			self._exiting = False
		return suppress

	def _enter(self):
		# noinspection PyUnresolvedReferences
		return super().__enter__()

	def _exit(self, exc_type, exc_val, exc_tb):
		# noinspection PyUnresolvedReferences
		return super().__exit__(exc_type, exc_val, exc_tb)

	@property
	def enter_result(self):
		return self._enter_result

	@property
	def enter_count(self):
		return self._enter_count

# Metaclass to allow easy definition of reentrant context managers
class ReentrantMeta(type):

	def __new__(mcs, name, bases, attrs):

		cls = super().__new__(mcs, name, bases, attrs)

		def apply_wrapper(method_name, wrapper):
			if method_name in attrs:
				orig_method = getattr(cls, method_name)
				@functools.wraps(orig_method)
				def new_method(self, *args, **kwargs):
					if type(self) is cls:
						return wrapper(self, orig_method, args, kwargs)
					else:
						return orig_method(self, *args, **kwargs)
				setattr(cls, method_name, new_method)
			else:
				@instance_method_of(cls, name=method_name)
				def new_method(self, *args, **kwargs):
					if type(self) is cls:
						return wrapper(self, getattr(super(cls, self), method_name).__func__, args, kwargs)
					else:
						return getattr(super(cls, self), method_name)(*args, **kwargs)

		def init_wrapper(self, wrap, args, kwargs):
			self._enter_count = 0
			self._enter_result = None
			self._entering = False
			self._exiting = False
			wrap(self, *args, **kwargs)

		def enter_wrapper(self, wrap, args, kwargs):
			try:
				self._entering = True
				self._enter_count += 1
				if self._enter_count == 1:
					self._enter_result = wrap(self, *args, **kwargs)
			finally:
				self._entering = False
			return self._enter_result

		def exit_wrapper(self, wrap, args, kwargs):
			try:
				self._exiting = True
				if self._enter_count < 1:
					raise AssertionError("Reentrant context manager should not be exited more times than it is entered")
				elif self._enter_count == 1:
					suppress = wrap(self, *args, **kwargs)
					self._enter_result = None
				else:
					suppress = False
				self._enter_count -= 1
			finally:
				self._exiting = False
			return suppress

		apply_wrapper('__init__', init_wrapper)
		apply_wrapper('__enter__', enter_wrapper)
		apply_wrapper('__exit__', exit_wrapper)

		return cls
# EOF
