# Imports
import sys
import traceback
import contextlib

def enter_foo_actions():
	print("ENTERING FOO")
	# raise ValueError("Failed to enter Foo")
	return 42

def enter_bar_actions():
	print("ENTERING BAR")
	# raise ValueError("Failed to enter Bar")

# noinspection PyUnusedLocal
def exit_foo_actions(exc_type, exc_val, exc_tb):
	print(f"EXITING FOO: {exc_type} {exc_val}")
	# raise ValueError("Failed to exit Foo")
	# return True
	return False

# noinspection PyUnusedLocal
def exit_bar_actions(exc_type, exc_val, exc_tb):
	print(f"EXITING BAR: {exc_type} {exc_val}")
	# raise ValueError("Failed to exit Bar")
	# return True
	return False

def with_actions(value):
	print(f"INSIDE WITH STATEMENT {value}")
	# raise ValueError("Failed inside with statement")

class Foo:

	def __enter__(self):
		return enter_foo_actions()

	def __exit__(self, exc_type, exc_val, exc_tb):
		return exit_foo_actions(exc_type, exc_val, exc_tb)

class RawBar:

	def __enter__(self):
		return enter_bar_actions()

	def __exit__(self, exc_type, exc_val, exc_tb):
		return exit_bar_actions(exc_type, exc_val, exc_tb)

class Bar(Foo):

	def __init__(self):
		self.stack = contextlib.ExitStack()

	def __enter__(self):
		with self.stack as stack:
			ret = super().__enter__()
			stack.push(super().__exit__)
			enter_bar_actions()
			stack.push(exit_bar_actions)
			self.stack = stack.pop_all()
		assert self.stack is not stack
		return ret

	def __exit__(self, exc_type, exc_val, exc_tb):
		return self.stack.__exit__(exc_type, exc_val, exc_tb)

# Main function
# noinspection PyTypeChecker
def main():

	try:
		print("BEFORE WITH STATEMENT")
		with Bar() as value:
			with_actions(value)
		print("AFTER WITH STATEMENT")
	except ValueError:
		traceback.print_exc()

	print("-" * 80)

	try:
		print("BEFORE WITH STATEMENT")
		with Foo() as value, RawBar():
			with_actions(value)
		print("AFTER WITH STATEMENT")
	except ValueError:
		traceback.print_exc()

	print("-" * 80)

	try:
		print("BEFORE WITH STATEMENT")
		with contextlib.ExitStack() as stack:
			value = stack.enter_context(Foo())
			stack.enter_context(RawBar())
			with_actions(value)
		print("AFTER WITH STATEMENT")
	except ValueError:
		traceback.print_exc()

# Run main function
if __name__ == '__main__':
	sys.exit(0 if main() else 1)
# EOF
