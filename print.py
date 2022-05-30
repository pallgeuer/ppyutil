# Print utilities

# Imports
import sys
import pprint
from shutil import get_terminal_size
from colored import stylize, fg as setfg, bg as setbg, attr as setatt
from timeit import default_timer
from ppyutil.interpreter import is_notebook

# Fixed printable width used for notebooks
notebook_width = 96

# Print a string with certain color attributes
def printc(text, fg=None, bg=None, attr=None):
	style = ''
	if fg:
		style += setfg(fg)
	if bg:
		style += setbg(bg)
	if attr:
		style += setatt(attr)
	print(stylize(text, style))

# Print to stderr
def eprint(*args, **kwargs):
	file = kwargs.get('file', None)
	if file is None:
		kwargs['file'] = sys.stderr
	print(*args, **kwargs)

# Print colored warning message to stdout
def print_warn(warn, prefix=True, **kwargs):
	if prefix:
		print(stylize(f"[WARN] {warn}", setfg(166)), **kwargs)
	else:
		print(stylize(f"{warn}", setfg(166)), **kwargs)

# Print colored error message to stderr
def print_error(error):
	eprint(stylize(f"[ERROR] {error}", setfg(1)))

# Print colored debug message to stdout
def print_debug(debug):
	print(stylize(f"[DEBUG] {debug}", setfg(2)))

# Print a horizontal line
def print_hor_line(fg=None, bg=None, attr=None, **kwargs):
	printc('-' * get_printable_width(**kwargs), fg, bg, attr)

# In-place printing (replace the current line and don't advance to the next line)
def print_in_place(obj):
	print(f"\x1b[2K\r{obj}", end='')

# Clear current line
def print_clear_line():
	print("\x1b[2K\r", end='')

# Determine current width of printable area
def get_printable_width(notebook=notebook_width):
	if is_notebook():
		return notebook
	else:
		return get_terminal_size().columns

# Pretty print to the current printable width
def pprint_to_width(*args, notebook=notebook_width, **kwargs):
	pprint.pprint(*args, width=get_printable_width(notebook), **kwargs)

# Print a list using multiple columns (assumes no element in the list or prefix has newline or line feed characters etc)
def print_as_columns(obj_list, cols=None, max_cols=None, col_width=None, truncate=False, line_prefix=None, col_sep=2, line_postfix=None, cell_align='<', notebook=notebook_width):
	# obj_list = List of strings or other objects to print using columns (should all have single-line string representations)
	# cols = Number of columns to use (None => Auto)
	# max_cols = Maximum number of columns to auto-select
	# col_width = Column width to use (None => Auto)
	# truncate = Whether to truncate strings to ensure they fit to the column width
	# line_prefix = String to print at the start of every row (None => No prefix)
	# col_sep = String to print as the column separator (int => Number of spaces)
	# line_postfix = String to print at the end of every row (None => No postfix)
	# cell_align = Cell alignment to use ('<' = Left align, '^' = Center align, '>' = Right align)
	# notebook = Printable width to assume if this code is running in a notebook

	str_list = [str(obj) for obj in obj_list]
	if not str_list:
		return

	col_sep = ' ' * max(col_sep, 1) if isinstance(col_sep, int) else str(col_sep)
	len_col_sep = len(col_sep)
	line_prefix = '' if line_prefix is None else str(line_prefix)
	line_postfix = '' if line_postfix is None else str(line_postfix)
	fix_size = len(line_prefix) + len(line_postfix)

	printable_width = get_printable_width(notebook=notebook)
	reqd_col_width = max(len(obj_str) for obj_str in str_list)

	if cols is None:
		if col_width is None:
			col_width = reqd_col_width
		cols = (printable_width - fix_size + len_col_sep) // (col_width + len_col_sep)
		if max_cols is not None and max_cols >= 1:
			cols = min(cols, max_cols)
		cols = max(cols, 1)
	else:
		cols = max(cols, 1)
		if col_width is None:
			col_width = min(reqd_col_width, (printable_width - fix_size - (cols - 1) * len_col_sep) // cols)
	col_width = max(col_width, 1)

	rows = (len(str_list) - 1) // cols + 1
	lines = [str_list[i::rows] for i in range(rows)]
	for line in lines:
		line.extend([''] * (cols - len(line)))
		print(f"{line_prefix}{col_sep.join(f'{l[:col_width] if truncate else l:{cell_align}{col_width}s}' for l in line)}{line_postfix}")

# Prefixed print
class PrefixedPrinter:

	def __init__(self, line_prefix, stream=None):
		self.line_prefix = line_prefix
		self.stream = stream
		self.prefix = True

	def __call__(self, *args, **kwargs):
		print(*args, file=self, **kwargs)

	def write(self, data):
		stream = self.stream or sys.stdout
		lines = data.splitlines(True)
		for line in lines:
			if self.prefix:
				stream.write(self.line_prefix)
			self.prefix = True
			stream.write(line)
		if lines:
			last_line = lines[-1].splitlines(False)
			self.prefix = last_line and last_line[0] != lines[-1]

	def writelines(self, lines):
		self.write(''.join(lines))

	def flush(self):
		stream = self.stream or sys.stdout
		stream.flush()

	def __getattr__(self, attr):
		stream = self.stream or sys.stdout
		return getattr(stream, attr)

# Timed print
class TimedPrinter:

	def __init__(self, start=True, stream=None):
		self.stream = stream
		self.prefix = True
		self.start_time = None
		if start:
			self.start()

	def start(self):
		self.start_time = default_timer()

	def stop(self):
		self.start_time = None

	def current_time(self):
		return default_timer() - self.start_time

	def __call__(self, *args, **kwargs):
		print(*args, file=self, **kwargs)

	def write(self, data):
		stream = self.stream or sys.stdout
		line_prefix = '[NaN] ' if self.start_time is None else f'[{self.current_time():.1f}s] '
		lines = data.splitlines(True)
		for line in lines:
			if self.prefix:
				stream.write(line_prefix)
			self.prefix = True
			stream.write(line)
		if lines:
			last_line = lines[-1].splitlines(False)
			self.prefix = last_line and last_line[0] != lines[-1]

	def writelines(self, lines):
		self.write(''.join(lines))

	def flush(self):
		stream = self.stream or sys.stdout
		stream.flush()

	def __getattr__(self, attr):
		stream = self.stream or sys.stdout
		return getattr(stream, attr)
# EOF
