# 3D rotation conversions

# Imports
import math
from enum import Enum, auto
import numpy as np

# Constants
twopi = 2 * math.pi

# Axis enumeration
class Axis(Enum):
	X = auto()
	Y = auto()
	Z = auto()

# Wrap an angle to (-pi, pi]
def wrap(angle):
	return math.pi - (math.pi - angle) % twopi

# Calculate fused yaw of rotation matrix
def fyaw_of_rotmat(R):
	t = R[0, 0] + R[1, 1] + R[2, 2]
	if t >= 0:
		fyaw = 2 * math.atan2(R[1, 0] - R[0, 1], 1 + t)
	elif R[2, 2] >= R[1, 1] and R[2, 2] >= R[0, 0]:
		fyaw = 2 * math.atan2(1 - R[0, 0] - R[1, 1] + R[2, 2], R[1, 0] - R[0, 1])
	elif R[1, 1] >= R[0, 0]:
		fyaw = 2 * math.atan2(R[2, 1] + R[1, 2], R[0, 2] - R[2, 0])
	else:
		fyaw = 2 * math.atan2(R[0, 2] + R[2, 0], R[2, 1] - R[1, 2])
	return wrap(fyaw)

# Calculate rotation matrix from axis-angle specification
def rotmat_from_axis(axis, angle):
	cang = math.cos(angle)
	sang = math.sin(angle)
	if axis == Axis.X:
		return np.array(((1, 0, 0), (0, cang, -sang), (0, sang, cang)))
	elif axis == Axis.Y:
		return np.array(((cang, 0, sang), (0, 1, 0), (-sang, 0, cang)))
	elif axis == Axis.Z:
		return np.array(((cang, -sang, 0), (sang, cang, 0), (0, 0, 1)))
	else:
		raise ValueError(f"Unrecognised axis specification: {axis}")
# EOF
