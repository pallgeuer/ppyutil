# OpenCV utilities

# Imports
import base64
from typing import Tuple
import numpy as np
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

# Encode an image to string
def image_to_string(image, base=85, encoding='.png', encoding_params=None):
	if image.dtype == np.bool:
		image = image.view(np.ubyte)
	retval, buffer = cv2.imencode(encoding, image, params=encoding_params)
	if not retval:
		raise ValueError(f"Failed to encode image as {encoding} with params {encoding_params}")
	if base == 16:
		enc_buffer = base64.b16encode(buffer)
	elif base == 32:
		enc_buffer = base64.b32encode(buffer)
	elif base == 64:
		enc_buffer = base64.b64encode(buffer)
	elif base == 85:
		enc_buffer = base64.b85encode(buffer)
	else:
		raise ValueError(f"Invalid encoding base: {base}")
	return enc_buffer.decode('ascii')

# Decode an image from string
def image_from_string(string, base=85):
	enc_buffer = string.encode('ascii')
	if base == 16:
		buffer = base64.b16decode(enc_buffer)
	elif base == 32:
		buffer = base64.b32decode(enc_buffer)
	elif base == 64:
		buffer = base64.b64decode(enc_buffer)
	elif base == 85:
		buffer = base64.b85decode(enc_buffer)
	else:
		raise ValueError(f"Invalid decoding base: {base}")
	return cv2.imdecode(np.frombuffer(buffer, dtype=np.ubyte), cv2.IMREAD_ANYCOLOR)

# Compress an image to string
def compress_to_string(image, lossless=True, bilevel=False):
	if lossless:
		return image_to_string(image, base=85, encoding='.png', encoding_params=(cv2.IMWRITE_PNG_COMPRESSION, 9, cv2.IMWRITE_PNG_BILEVEL, 1 if bilevel or image.dtype == np.bool else 0))
	else:
		return image_to_string(image, base=85, encoding='.jpg', encoding_params=(cv2.IMWRITE_JPEG_QUALITY, 80, cv2.IMWRITE_JPEG_OPTIMIZE, 1))

# Uncompress a string to image
def uncompress_from_string(string, bilevel=False):
	image = image_from_string(string, base=85)
	if bilevel:
		image = image.astype(bool)
	return image
# EOF
