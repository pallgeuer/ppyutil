# Imports
import sys
import time
import numpy as np
import multiprocessing

# Constants
MP = multiprocessing.get_context('forkserver')

# Main function
def main():

	image_size = (640, 480)
	lock = MP.RLock()

	image_array = MP.Array('B', image_size[0] * image_size[1] * 3, lock=False)
	image = np.frombuffer(image_array, dtype='B').reshape((image_size[1], image_size[0], 3))

	image.fill(77)
	print(f"MAIN A: {image[0,0]}")

	image_other = np.frombuffer(image_array, dtype='B').reshape((image_size[1], image_size[0], 3))
	proc = MP.Process(target=subprocess_run, args=(image_size, image_array, lock, image_other), daemon=True)
	proc.start()

	time.sleep(1)

	with lock:
		print(f"MAIN B: {image[0,0]}")
		image.fill(44)
		print(f"MAIN C: {image[0,0]}")

	time.sleep(5)

	with lock:
		print(f"MAIN D: {image[0,0]}")

	proc.join()

	return True

# Subprocess run
def subprocess_run(image_size, image_array, lock, image_other):
	image = np.frombuffer(image_array, dtype='B').reshape((image_size[1], image_size[0], 3))
	with lock:
		print(f"SUB A: {image[0,0]} vs {image_other[0,0]}")
	time.sleep(3)
	with lock:
		print(f"SUB B: {image[0,0]} vs {image_other[0,0]}")
		image.fill(11)
		print(f"SUB C: {image[0,0]} vs {image_other[0,0]}")
	time.sleep(5)
	with lock:
		print(f"SUB D: {image[0,0]} vs {image_other[0,0]}")

# Run main function
if __name__ == '__main__':
	sys.exit(0 if main() else 1)
# EOF
