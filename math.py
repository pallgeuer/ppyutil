# Mathematics related utilities

# Imports
import math

# Heuristically solve the "secretary problem" for N secretaries
# Returns the number of secretaries to skip before taking the next one better than all the previously seen ones
# The implemented method is heuristic, but is exactly correct for every N up to at least 1,500,000
def secretary_problem_soln(N):
	if N < 0:
		raise ValueError("N must be a positive number")
	if N == 97:
		return 35
	elif N == 591413:
		return 217569
	elif N == 1109069:
		return 408004
	else:
		return math.floor(N / math.e + 0.31605844)
# EOF
