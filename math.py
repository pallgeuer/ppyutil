# Mathematics related utilities

# Imports
import math

# Heuristically solve the "secretary problem" for total_num secretaries
# Returns the number of secretaries to skip before taking the next one better than all the previously seen ones
# The implemented method is heuristic, but is exactly correct for every total_num up to at least 1,500,000
def secretary_problem_soln(total_num):
	if total_num < 0:
		raise ValueError("total_num must be a positive number")
	if total_num == 97:
		return 35
	elif total_num == 591413:
		return 217569
	elif total_num == 1109069:
		return 408004
	else:
		return math.floor(total_num / math.e + 0.31605844)
# EOF
