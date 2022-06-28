# OpenCV utilities

# Imports
from typing import Tuple
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

	def __init__(self, filename: str, fourcc: int, fps: float, frame_size: Tuple[int, int], *args, api_pref: int = cv2.CAP_ANY):
		self.filename = filename
		self.api_pref = api_pref
		self.fourcc = fourcc
		self.fps = fps
		self.frame_size = frame_size
		self.args = args
		self.writer = None

	def __getattr__(self, item):
		if self.writer:
			return getattr(self.writer, item)
		else:
			raise AttributeError

	def __enter__(self):
		self.writer = cv2.VideoWriter(self.filename, self.api_pref, self.fourcc, self.fps, self.frame_size, *self.args)
		return self

	def __exit__(self, *args):
		if self.writer:
			self.writer.release()
			self.writer = None
# EOF
