#!/usr/bin/env python3
# Test util.contextman

# Imports
import sys
import time
import random
import functools
from pprint import pprint
from types import MethodType
import contextlib
import util.contextman

#
# Test DynamicContext
#

class ContextClass:

	def __init__(self, name, show_init=False, exc_enter=False, exc_exit=False, exc_suppress=False):
		self.name = name
		if show_init:
			print(f"Initing: {self.name}")
		self.exc_enter = exc_enter
		self.exc_exit = exc_exit
		self.exc_suppress = exc_suppress

	def __enter__(self):
		result = ord(self.name[0])
		print(f"Entering: {self.name} (result {result})")
		if self.exc_enter:
			raise ValueError("Exception during enter")
		return result

	def __exit__(self, exc_type, exc_val, exc_tb):
		print(f"Exiting: {self.name} (exc {exc_type.__name__ if exc_type else exc_type})")
		if self.exc_exit:
			raise ValueError("Exception during exit")
		return self.exc_suppress

@contextlib.contextmanager
def decorated_context(name):
	result = ord(name[0])
	print(f"Entering: {name} (decorated result {result})")
	try:
		yield result
	finally:
		print(f"Exiting: {name} (decorated)")

# noinspection PyUnusedLocal
def custom_exit_func(name, exc_type, exc_val, exc_tb):
	print(f"Exiting: {name} (exit func exc {exc_type.__name__ if exc_type else exc_type})")
	return False

def callback_func(name):
	print(f"Exiting: {name} (callback)")
	return True  # Should be ignored and not cause an exception to be suppressed

def build_dyncon(nodes):
	print('-' * 80)
	nodes.clear()
	context = util.contextman.DynamicContext()
	nodes['A'] = context.enter_context(ContextClass('A'), key='A')
	nodes['B'] = context.enter_context(ContextClass('B'))
	nodes['C'] = context.register_callback(callback_func, 'C', key='C', parent=nodes['A'])
	nodes['D'] = context.enter_context(decorated_context('D'), key='D', parent=nodes['C'])
	nodes['E'] = context.register_exit_func(functools.partial(custom_exit_func, 'E'), key='E')
	nodes['F'] = context.enter_context(ContextClass('F'), parent=nodes['A'])
	nodes['G'] = context.enter_context(ContextClass('G'), key='G', parent=nodes['E'])
	nodes['H'] = context.enter_context(ContextClass('H'), key='H', parent=nodes['F'])
	nodes['I'] = context.register_exit_func(ContextClass('I').__exit__, parent=nodes['G'])
	nodes['J'] = context.enter_context(ContextClass('J'), key='J', parent=nodes['E'])
	nodes['K'] = context.enter_context(ContextClass('K'))
	nodes['L'] = context.enter_context(ContextClass('L'), key='L', parent=nodes['K'])
	return context

# noinspection PyUnreachableCode
def test_DynamicContext():

	print("Testing DynamicContext class")

	nodes = {}
	random.seed(40)

	with build_dyncon(nodes) as DC:
		print("INSIDE WITH BLOCK")
		pprint(nodes)
		pprint(DC.key_dict())
		print(DC.keys())
		pprint(list(DC.keys()))
		print(DC.key_items())
		pprint(list(DC.key_items()))
		print(DC['C'])
		print(None in DC)
		print('B' in DC)
		print('G' in DC)
		print(DC.get('B', 'B is not there'))
		print(DC.get('G', 'G is not there'))
		print(DC.get('K'))
		print(DC.get(None))
		try:
			print(f">>{DC[None]}")
		except KeyError:
			print("KeyError was raised while getting item None")
		try:
			print(f">>{DC['K']}")
		except KeyError:
			print("KeyError was raised while getting item 'K'")
		time.sleep(2)
		print("END WITH BLOCK")

	try:
		with build_dyncon(nodes):
			print("INSIDE WITH BLOCK")
			raise ValueError("Bad")
			print("END WITH BLOCK")
	except Exception as e:
		print(f"Caught: {type(e).__name__} => {e}")

	with build_dyncon(nodes) as DC:
		print("INSIDE WITH BLOCK")
		DC.leave_context(nodes['A'])
		print("=" * 20)
		DC.close_exit_func(nodes['E'])
		print("END WITH BLOCK")

	try:
		with build_dyncon(nodes) as DC:
			print("INSIDE WITH BLOCK")
			DC.close_callback(nodes['C'])
			print("=" * 20)
			DC.close_node(nodes['F'])
			print("=" * 20)
			DC.close_node(None)
			print("END WITH BLOCK")
	except Exception as e:
		print(f"Caught: {type(e).__name__} => {e}")

	try:
		with build_dyncon(nodes) as DC:
			print("INSIDE WITH BLOCK")
			DC.close_nodes(nodes['C'], (nodes['H'], nodes['D']), {nodes['J']}, [nodes['I'], nodes['E']])
			print("=" * 20)
			DC.close_all()
			print("=" * 20)
			nodes['M'] = DC.enter_context(ContextClass('M'))
			print("=" * 20)
			print("L active:", DC.is_active_node(nodes['L']))
			print("M active:", DC.is_active_node(nodes['M']))
			nodes['M'] = DC.enter_context(ContextClass('N'), parent=nodes['L'])
			print("END WITH BLOCK")
	except Exception as e:
		print(f"Caught: {type(e).__name__} => {e}")

	with build_dyncon(nodes) as DC:
		print("INSIDE WITH BLOCK")
		cb_E = DC.pop_node(nodes['E'])
		print("=" * 20)
		DC.close_node(nodes['G'])
		print("=" * 20)
		cb_F = DC.pop_node(nodes['F'])
		print("=" * 20)
		DC.close_node(nodes['A'])
		print("END WITH BLOCK")
	print("Manually exiting E")
	cb_E(None, None, None)
	print("Manually exiting F")
	cb_F(None, None, None)

	with build_dyncon(nodes) as DC:
		print("INSIDE WITH BLOCK")
		DCnew = DC.pop_all()
		print("=" * 20)
		nodes['M'] = DC.enter_context(ContextClass('M'))
		print("L active:", DC.is_active_node(nodes['L']))
		print("M active:", DC.is_active_node(nodes['M']))
		print("L active (new):", DCnew.is_active_node(nodes['L']))
		print("M active (new):", DCnew.is_active_node(nodes['M']))
		print("END WITH BLOCK")
	with DCnew:
		print("INSIDE WITH BLOCK")
		nodes['N'] = DCnew.enter_context(ContextClass('N'), parent=nodes['B'])
		print("END WITH BLOCK")

	for i in range(6):
		with build_dyncon(nodes) as DC:
			nodes['M'] = DC.enter_context(ContextClass('M'), parent=nodes['H'])
			nodes['N'] = DC.enter_context(ContextClass('N'), parent=nodes['M'])
			print(f"RANDOM POP {i + 1}")
			print("INSIDE WITH BLOCK")
			nodes_list = list(nodes.items())
			# noinspection PyUnusedLocal
			to_pop_i = [random.randint(0, len(nodes_list) - 1) for j in range(random.randint(0, 6))]
			to_pop = [nodes_list[i][1] for i in to_pop_i]
			children = random.random() < 0.5
			print("Popping:", ', '.join(nodes_list[i][0] for i in to_pop_i))
			print("Plus children:", children)
			DCnew = DC.pop_nodes(to_pop, children=children)
			print("=" * 20)
			if DC.is_active_node(nodes['A']):
				DC.close_node(nodes['A'])
			print("END WITH BLOCK")
		with DCnew:
			print("INSIDE WITH BLOCK")
			print("END WITH BLOCK")

	try:
		with build_dyncon(nodes) as DC:
			print("INSIDE WITH BLOCK")
			nodes['M'] = DC.enter_context(ContextClass('M', exc_enter=True), parent=nodes['H'])
			print("END WITH BLOCK")
	except Exception as e:
		print(f"Caught: {type(e).__name__} => {e}")

	try:
		with build_dyncon(nodes):
			print("INSIDE WITH BLOCK")
			nodes['F'].obj.exc_exit = True
			print("END WITH BLOCK")
	except Exception as e:
		print(f"Caught: {type(e).__name__} => {e}")

	try:
		with build_dyncon(nodes) as DC:
			print("INSIDE WITH BLOCK")
			nodes['G'].obj.exc_exit = True
			nodes['J'].obj.exc_suppress = True
			nodes['M'] = DC.enter_context(ContextClass('M', exc_exit=True), parent=nodes['H'])
			DC.close_node(nodes['F'])
			print("END WITH BLOCK")
	except Exception as e:
		print(f"Caught: {type(e).__name__} => {e}")

	print("End of testing")

#
# Test context wrappers
#

def test_ContextWrappers():

	print("Creating cm")
	cm = ContextClass('Printy', show_init=True)
	print("Before with statement")
	with cm as result:
		print(f"cm = {cm}")
		print(f"result = {result}")
	print("Outside with statement again")

	print('-' * 60)

	print("Creating cm (ConstructOnEnter)")
	cm = util.contextman.ConstructOnEnter(ContextClass, 'Printy', show_init=True)
	print("Before with statement")
	with cm as result:
		print(f"cm = {cm}")
		print(f"real cm = {cm.wrapped_context()}")
		print(f"result = {result}")
	print("Outside with statement again")

	print('-' * 60)

	print("Creating cm (MakeReentrant)")
	cm = util.contextman.MakeReentrant(ContextClass('Printy', show_init=True))
	print("Before with statement")
	with cm as result:
		print(f"cm = {cm}")
		print(f"real cm = {cm.wrapped_context()}")
		print(f"result = {result}")
		with cm as resultt:
			with cm as resulttt:
				print(f"cm = {cm}")
				print(f"real cm = {cm.wrapped_context()}")
				print(f"result = {resulttt}")
			print(f"cm = {cm}")
			print(f"real cm = {cm.wrapped_context()}")
			print(f"result = {resultt}")
	print("Outside with statement again")

	print('-' * 60)

	print("Creating cm (MakeReentrant + ConstructOnEnter)")
	cm = util.contextman.MakeReentrant(util.contextman.ConstructOnEnter(ContextClass, 'Printy', show_init=True))
	print("Before with statement")
	with cm as result:
		print(f"cm = {cm}")
		print(f"real cm = {cm.wrapped_context()}")
		print(f"result = {result}")
		with cm as resultt:
			with cm as resulttt:
				print(f"cm = {cm}")
				print(f"real cm = {cm.wrapped_context()}")
				print(f"result = {resulttt}")
			print(f"cm = {cm}")
			print(f"real cm = {cm.wrapped_context()}")
			print(f"result = {resultt}")
	print("Outside with statement again")

#
# Test ReentrantBase
#

class Pure(util.contextman.ReentrantBase):

	def __init__(self):
		super().__init__()
		print("[Pure] Init")

	def _enter(self):
		print("[Pure] MY ENTER CODE")
		return self

	def _exit(self, exc_type, exc_val, exc_tb):
		print("[Pure] MY EXIT CODE")

class OneShot:

	def __init__(self):
		print("[OneShot] Init")

	def __enter__(self):
		print("[OneShot] MY ENTER CODE")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[OneShot] MY EXIT CODE")
		return False

class MultiShot(util.contextman.ReentrantBase, OneShot):
	pass

class ClassA:

	def __init__(self):
		super().__init__()
		print("[ClassA] Init")

	def __enter__(self):
		print("[ClassA] __enter__")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[ClassA] __exit__")
		return False

	def foo(self):
		print(f"FOO: {self}")

class ClassB(ClassA):

	def __init__(self, need):
		super().__init__()
		print(f"[ClassB] Init {need}")

	def __enter__(self):
		print("[ClassB] __enter__ START")
		super().__enter__()
		print("[ClassB] __enter__ END")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[ClassB] __exit__ START")
		super().__exit__(exc_type, exc_val, exc_tb)
		print("[ClassB] __exit__ END")
		return False

class ClassC(util.contextman.ReentrantBase, ClassB):

	def __init__(self, blah, other):
		super().__init__(blah + other)
		print(f"[ClassC] Init {blah} {other}")

	def _enter(self):
		print("[ClassC] _enter START")
		super().__enter__()
		print("[ClassC] _enter END")
		return self

	def _exit(self, exc_type, exc_val, exc_tb):
		print("[ClassC] _exit START")
		super().__exit__(exc_type, exc_val, exc_tb)
		print("[ClassC] _exit END")
		return False

class ClassD(ClassC):

	def __init__(self):
		super().__init__(7, 11)
		print(f"[ClassD] Init")

	def _enter(self):
		print("[ClassD] _enter START")
		super()._enter()
		print("[ClassD] _enter END")
		return self

	def _exit(self, exc_type, exc_val, exc_tb):
		print("[ClassD] _exit START")
		super()._exit(exc_type, exc_val, exc_tb)
		print("[ClassD] _exit END")
		return False

def test_ReentrantBase():

	print()

	print("With Pure:")
	P = Pure()
	with P as p:
		print(f"  p is {p}")
		with P as pp:
			print(f"  pp is {pp}")
		print(f"  p is {p}")
	print()

	print("With OneShot:")
	OS = OneShot()
	with OS as o:
		print(f"  o is {o}")
		with OS as oo:
			print(f"  oo is {oo}")
		print(f"  o is {o}")
	print()

	print("With MultiShot:")
	MS = MultiShot()
	with MS as m:
		print(f"  m is {m}")
		with MS as mm:
			print(f"  mm is {mm}")
		print(f"  m is {m}")
	print()

	print("Creating a D:")
	D = ClassD()
	print()

	print("Creating a C:")
	ClassC(4, 9)
	print()

	print("With D:")
	with D as d:
		print(f"  d is {d}")
		with D as dd:
			print(f"  dd is {dd}")
		print(f"  d is {d}")
	print()

#
# Test ReentrantMeta
#

class RMA:

	def __init__(self):
		print("[RMA] Init")

	def __enter__(self):
		print("[RMA] Enter")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[RMA] Exit")
		return False

class RMB(RMA, metaclass=util.contextman.ReentrantMeta):

	def __init__(self):
		print(f"[RMB] Preinit")
		super().__init__()
		print("[RMB] Init")

	def __enter__(self):
		print("[RMB] Enter START")
		result = super().__enter__()
		print("[RMB] Enter END")
		return result

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[RMB] Exit START")
		suppress = super().__exit__(exc_type, exc_val, exc_tb)
		print("[RMB] Exit END")
		return suppress

class RMC(RMB):

	def __init__(self):
		print("[RMC] Preinit")
		super().__init__()
		print("[RMC] Init")

	def __enter__(self):
		print("[RMC] Enter START")
		result = super().__enter__()
		print("[RMC] Enter END")
		return result

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[RMC] Exit START")
		suppress = super().__exit__(exc_type, exc_val, exc_tb)
		print("[RMC] Exit END")
		return suppress

def test_ReentrantMeta():

	print()

	print("CREATE RMA:")
	RMA()
	print()
	print("CREATE RMB:")
	RMB()
	print()
	print("CREATE RMC:")
	RMC()
	print()

	# noinspection PyUnusedLocal
	def custom(self):
		print("[RMA] Init (custom)")

	RMA.__init__ = custom

	print("CREATE RMA:")
	RMA()
	print()
	print("CREATE RMB:")
	RMB()
	print()
	print("CREATE RMC:")
	RMC()
	print()

	print(f"RMA: {type(RMA)}")
	print(f"RMB: {type(RMB)}")
	print(f"RMC: {type(RMC)}")
	print()

	pprint(vars(RMA))
	pprint(vars(RMB))
	pprint(vars(RMC))
	print()

	def test_RM(cls, *args, **kwargs):
		print(f"With {cls.__name__}:")
		C = cls(*args, **kwargs)
		print("---")
		with C as res:
			print(f"  res is {res}")
			with C as ress:
				print(f"  ress is {ress}")
			print(f"  res is {res}")
		print()

	test_RM(RMA)
	test_RM(RMB)
	test_RM(RMC)

#
# Test CM subclassing strategy
#

# Note: Depending on what you're doing, it might be easier to just use a decorated function CM with nested with statements.
#       It may also be appropriate to just use a DynamicContext to test various CMs within each other, instead of explicitly subclassing. They can still use info from each other.

class SubA:

	def __init__(self, error):
		print(f"[SubA] Init")
		self._printy = 0
		self._printy_error = error

	def __enter__(self):
		with contextlib.ExitStack() as stack:
			print("[SubA] Enter")
			stack.push(MethodType(SubA.__exit__, self))
			self.printy(f"Acquire ResA")
			self.printy(f"Process ResA")
			stack.pop_all()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		print("[SubA] Exit:", exc_val)
		self.printy(f"Release ResA if it was acquired")
		return False

	def printy(self, *args, **kwargs):
		self._printy += 1
		error = (self._printy == self._printy_error)
		if error:
			print(self._printy, '=>', *args, "--> ValueError", **kwargs)
			raise ValueError(f"Errored at {self._printy}")
		else:
			print(self._printy, '=>', *args, **kwargs)

class SubB(SubA):

	def __init__(self, error):
		super().__init__(error)
		print(f"[SubB] Init")

	def __enter__(self):
		with contextlib.ExitStack() as stack:
			print("[SubB] Enter")
			result = super().__enter__()
			stack.push(MethodType(SubB.__exit__, self))
			self.printy(f"Acquire ResB")
			self.printy(f"Process ResB")
			stack.pop_all()
		return result

	def __exit__(self, exc_type, exc_val, exc_tb):
		# Note: Depending on how ResB relates to ResA, you may wish to use an ExitStack to ensure that ResA
		#       is still released (super().__exit__) even if the releasing code of ResB raises an exception.
		print("[SubB] Exit:", exc_val)
		self.printy(f"Release ResB if it was acquired")
		suppress = super().__exit__(exc_type, exc_val, exc_tb)
		return suppress

class SubC(SubB):

	def __init__(self, error):
		super().__init__(error)
		print(f"[SubC] Init")

	def __enter__(self):
		with contextlib.ExitStack() as stack:
			print("[SubC] Enter")
			result = super().__enter__()
			stack.push(MethodType(SubC.__exit__, self))
			self.printy(f"Acquire ResC")
			self.printy(f"Process ResC")
			stack.pop_all()
		return result

	def __exit__(self, exc_type, exc_val, exc_tb):
		# Note: This is an example of the call to super().__exit__ being important even if releasing ResC raises
		#       an (expected) exception. This should not be done just to handle KeyboardInterrupt, which is better
		#       dealt with using signals.DeferSignals, but only if it's REALLY important (you can never make it
		#       100% anyway, so it would just be a bandaid anyway).
		with contextlib.ExitStack() as stack:
			print("[SubC] Exit:", exc_val)
			stack.push(super().__exit__)
			self.printy(f"Release ResC if it was acquired")
			stack.pop_all()
			suppress = super().__exit__(exc_type, exc_val, exc_tb)
		return suppress

def test_SubclassStrategy():

	for error in range(4):
		if error > 0:
			print('-' * 80)
			print()
		try:
			with SubA(error + 1) as A:
				print(f"A = {A}")
		except ValueError:
			print("Caught ValueError")
		print()

	print('=' * 80)
	print()

	for error in range(7):
		if error > 0:
			print('-' * 80)
			print()
		try:
			with SubB(error + 1) as B:
				print(f"B = {B}")
		except ValueError:
			print("Caught ValueError")
		print()

	print('=' * 80)
	print()

	for error in range(10):
		if error > 0:
			print('-' * 80)
			print()
		try:
			with SubC(error + 1) as C:
				print(f"C = {C}")
		except ValueError:
			print("Caught ValueError")
		print()

#
# Main function
#

def main():
	print("BEGIN")
	# test_DynamicContext()
	# test_ContextWrappers()
	# test_ReentrantBase()
	# test_ReentrantMeta()
	test_SubclassStrategy()
	print("END")

if __name__ == "__main__":
	sys.exit(main())
# EOF
