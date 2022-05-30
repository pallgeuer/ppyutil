# OpenCV utilities

# Imports
import cv2

# Video capture context manager
class VideoCaptureCM:

	def __init__(self, *args, **kwargs):
		self.args = args
		self.kwargs = kwargs
		self.stream = None

	def __enter__(self):
		self.stream = cv2.VideoCapture(*self.args, **self.kwargs)
		return self.stream

	def __exit__(self, *args):
		if self.stream:
			self.stream.release()
			self.stream = None

# Video writer context manager
class VideoWriterCM:

	def __init__(self, *args, **kwargs):
		self.args = args
		self.kwargs = kwargs
		self.writer = None

	def __enter__(self):
		self.writer = cv2.VideoWriter(*self.args, **self.kwargs)
		return self.writer

	def __exit__(self, *args):
		if self.writer:
			self.writer.release()
			self.writer = None
# EOF
