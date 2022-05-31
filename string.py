# String utilities

# Imports
import re
import codecs
import unidecode

# Basic conversion of string to ranged integer
def ranged_int(string, imin=None, imax=None):
	value = int(string)  # Note: This may also raise a TypeError if 'string' is not a string
	if imin is not None and value < imin:
		raise ValueError(f"Value {value} is less than allowed minimum ({imin})")
	if imax is not None and value > imax:
		raise ValueError(f"Value {value} is greater than allowed maximum ({imax})")
	return value

# Safely convert a string to a non-negative integer (just use int() if the string already passed a regex and MUST be valid, returns None if it fails)
def parse_uint(string, clean=True):
	if clean:
		string = ''.join(s for s in string if s.isdecimal())
	try:
		value = int(string)
	except (ValueError, TypeError):
		return None
	return value if value >= 0 else None

# Safely convert a string to a float (just use float() if the string already passed a regex and MUST be valid, returns None if it fails)
def parse_float(string, clean=True):
	if clean:
		string = ''.join(string.split())
	try:
		return float(string)
	except (ValueError, TypeError):
		return None

# Remove whitespace from a string
def remove_spaces(string):
	return ''.join(string.split())

# Clean up whitespace in a string (converts all sequences of whitespace to a single space, and removes whitespace completely from the start and end of the string)
def clean_spaces(string):
	return ' '.join(string.split())

# Convert a string to its standard representation for comparisons (e.g. cleaning whitespace, removing accents, making lowercase and removing non-letter characters)
def clean_string(string):
	string = unidecode.unidecode(string).lower()
	string = re.sub(r'[^\w\s]', '', string)  # Remove all non-word/non-whitespace characters from the string
	string = clean_spaces(string)
	return string

# Clean up a string somewhat (lite version of clean_string above)
def clean_string_lite(string):
	string = unidecode.unidecode(string)
	string = clean_spaces(string)
	return string

# Convert a string representation of truth to a boolean
def strtobool(value):
	value = value.lower()
	if value in ('y', 'yes', 't', 'true', 'on', '1'):
		return True
	elif value in ('n', 'no', 'f', 'false', 'off', '0'):
		return False
	else:
		raise ValueError(f"Invalid truth value: {value}")

# Ensure that a string corresponds to a legal unix filename, making the minimal changes possible
# Resource: https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap03.html#tag_03_170
def ensure_filename(string):
	string = string.translate(str.maketrans('/', '_', '\0'))  # Convert '/' to '_' and remove null characters
	string = string.encode('utf-8')[:255].decode('utf-8', errors='ignore')  # Limit to 255 bytes (this will often correspond to less than 255 actual characters due to multibyte unicode characters)
	if string == '.' or string == '..':
		string = '...'
	if not string:
		string = '_'
	return string

# Capitalize the first letter of a string and leave the rest untouched (str.capitalize makes the rest lower case)
def capitalize_first(string):
	return string[:1].upper() + string[1:]

# Add a certain prefix to each line of a multiline string
def add_line_prefix(string, line_prefix, include_first_line=True):
	output = line_prefix.join(string.splitlines(True))
	if include_first_line:
		output = line_prefix + output
	return output

# Decode escape sequences in a string (e.g. replace every instance of sequential characters '\' and 'n' with the one newline character)
# Inspiration: https://stackoverflow.com/questions/4020539/process-escape-sequences-in-a-string-in-python
# noinspection RegExpRedundantEscape
EscapeSeqRegex = re.compile(r'''
	( \\U........      # 8-digit hex escapes
	| \\u....          # 4-digit hex escapes
	| \\x..            # 2-digit hex escapes
	| \\[0-7]{1,3}     # Octal escapes
	| \\N\{[^}]+\}     # Unicode characters by name
	| \\[\\'"abfnrtv]  # Single-character escapes
	| \\.              # Arbitrary single character escape
	)''', re.VERBOSE)
# noinspection RegExpRedundantEscape
EscapeSeqNameRegex = re.compile(r'''
	( U........      # 8-digit hex escapes
	| u....          # 4-digit hex escapes
	| x..            # 2-digit hex escapes
	| [0-7]{1,3}     # Octal escapes
	| N\{[^}]+\}     # Unicode characters by name
	| [\\'"abfnrtv]  # Single-character escapes
	)''', re.VERBOSE)
def decode_escapes(string):
	def decode_match(match):
		if EscapeSeqNameRegex.fullmatch(match.group(0), pos=1) is not None:
			return codecs.decode(match.group(0), 'unicode-escape')
		else:
			return match.group(0)[1:]
	return EscapeSeqRegex.sub(decode_match, string)
# EOF
