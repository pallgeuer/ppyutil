# Image plot utilities

# Imports
import json
import hashlib
from itertools import accumulate
import PIL.ImageDraw
import PIL.ImageFont
import matplotlib.pyplot as plt

# Constants
DefaultFont = 'NotoMono-Regular.ttf'

# Show generated plots
def show_plots():
	plt.show()

# Prepare image for plotting with imshow()
def prepare_image(image, **kwargs):
	# image = Image to plot (PIL image, NumPy array, Torch tensor), can be [0,1] or [0,255], can be RGB or greyscale
	# kwargs = Keyword arguments to pass to any internal calls to imshow() for this image
	# Return image suitable for imshow(), kwargs for imshow(), height in pixels, width in pixels, whether greyscale, whether normalised ([0, 1] instead of [0, 255])

	if hasattr(image, 'shape'):  # numpy.ndarray / torch.tensor
		if image.ndim == 3:
			if image.shape[0] < image.shape[2]:
				if hasattr(image, 'permute'):
					# noinspection PyCallingNonCallable
					image = image.permute(1, 2, 0)  # torch.tensor
				else:
					image = image.transpose(1, 2, 0)  # numpy.ndarray
			if image.shape[2] == 1:
				image = image.reshape(image.shape[0], image.shape[1])
		height = image.shape[0]
		width = image.shape[1]
		greyscale = (image.ndim == 2)
		normalised = (float(image.min()) >= -0.01 and float(image.max()) <= 1.01)
	elif hasattr(image, 'size'):  # PIL image
		width, height = image.size
		greyscale = (image.mode == 'L')
		normalised = False
	else:
		raise TypeError(f"Image does not have a 'size' or 'shape' attribute")

	if greyscale:
		kwargs.setdefault('cmap', 'gray')
		kwargs.setdefault('vmin', 0)
		kwargs.setdefault('vmax', 1 if normalised else 255)

	return image, kwargs, width, height, greyscale, normalised

# Plot an image pixel-perfect
def plot_image(image, scale=1.0, dpi=100, show=True, **kwargs):
	# image = Image to plot (see prepare_image() function)
	# scale = Scale multiplier to show the image at, e.g. 0.5 = half-size
	# dpi = Dots per inch to use (does not affect size on screen)
	# show = Whether to show the plotted image figure, or wait for a future manual call to plt.show() / show_plots()
	# kwargs = Keyword arguments to pass to internal call to imshow()

	image, imshow_kwargs, width, height, greyscale, normalised = prepare_image(image, **kwargs)

	fig = plt.figure(figsize=(scale*width/dpi, scale*height/dpi), dpi=dpi)
	ax = fig.add_axes([0, 0, 1, 1])
	ax.set_axis_off()
	ax.imshow(image, **imshow_kwargs)

	if show:
		plt.show()
		return None  # Intentionally not two None's to hopefully cause an exception if actually used
	else:
		return fig, ax

# Plot multiple PIL/tensor images side-by-side
def plot_images(images, plot_height=None, max_fig_width=1912, max_fig_height=918, dpi=100, show=True, **kwargs):
	# images = Iterable of images to plot side-by-side (see prepare_image() function)
	# plot_height = Pixel height to scale each image to (None => Plot each image in its original pixel height)
	# max_fig_width = Maximum figure width to allow in pixels
	# max_fig_height = Maximum figure height to allow in pixels
	# dpi = Dots per inch to use (does not affect size on screen)
	# show = Whether to show the plotted figure, or wait for a future manual call to plt.show() / show_plots()
	# kwargs = Keyword arguments to pass to all internal calls to imshow()

	prep_image = [prepare_image(image, **kwargs) for image in images]

	safety_margin = (len(prep_image) + 1) // 2
	max_fig_width -= safety_margin
	max_fig_height -= safety_margin

	if plot_height is None:
		ax_widths = [prep[2] for prep in prep_image]
		ax_heights = [prep[3] for prep in prep_image]
	elif plot_height >= 10:
		ax_widths = [prep[2] * plot_height / prep[3] for prep in prep_image]
		ax_heights = [plot_height] * len(prep_image)
	else:
		raise ValueError(f"Plot height should be at least 10 pixels: {plot_height}")

	fig_width = sum(ax_widths)
	fig_height = max(ax_heights)

	scale = min(max_fig_width / fig_width, max_fig_height / fig_height)
	if scale < 1:
		ax_widths = [w * scale for w in ax_widths]
		ax_heights = [h * scale for h in ax_heights]

	ax_widths = [round(w) for w in ax_widths]
	ax_heights = [round(h) for h in ax_heights]

	fig_width = sum(ax_widths)
	fig_height = max(ax_heights)

	ax_width_ratios = [w / fig_width for w in ax_widths]
	ax_pos = [0.0] + list(accumulate(ax_width_ratios))

	fig = plt.figure(figsize=(fig_width/dpi, fig_height/dpi), dpi=dpi)

	ax_list = []
	for i, prep in enumerate(prep_image):
		ax = fig.add_axes([ax_pos[i], 0, ax_width_ratios[i], 1])
		ax.set_axis_off()
		ax.imshow(prep[0], **prep[1])
		ax_list.append(ax)

	if show:
		plt.show()
		return None  # Intentionally not two None's to hopefully cause an exception if actually used
	else:
		return fig, ax_list

# Return whether two PIL images compare equal by mode, size and pixel value
def images_equal(image1, image2):
	if image1.mode != image2.mode or image1.size != image2.size:
		return False
	return all(p1 == p2 for p1, p2 in zip(image1.getdata(), image2.getdata()))

# Calculate an MD5 hash value for a PIL image
def image_hash(image):
	image_data = (image.mode, image.size, tuple(image.getdata()))
	return hashlib.md5(json.dumps(image_data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

# Ensure that a PIL image is in RGB mode (Careful: If the image is already in the required mode, the original UNCOPIED image is returned)
def ensure_rgb(image):
	return image if image.mode == 'RGB' else image.convert('RGB')

# Add a cross to a PIL image (useful for testing and visualisation purposes)
def add_cross(image, color='yellow'):
	draw = PIL.ImageDraw.Draw(image)
	draw.line((0, 0) + image.size, fill=color)
	draw.line((0, image.size[1], image.size[0], 0), fill=color)

# Add a title to a PIL image (draw onto the image)
def add_title(image, title, font_file=DefaultFont, font_height=0.04, color='yellow', position='top'):
	width, height = image.size
	draw = PIL.ImageDraw.Draw(image)
	image_font = PIL.ImageFont.truetype(font=font_file, size=round(font_height * height))
	tw, th = draw.textsize(title, font=image_font)
	if '\n' in title:
		th += image_font.getsize('p')[1] - image_font.getsize('A')[1]
	else:
		th = max(th, image_font.getsize('p')[1])
	if position == 'top':
		coords = ((width - tw) / 2, 0)
	elif position == 'bottom':
		coords = ((width - tw) / 2, height - th)
	elif position == 'center':
		coords = ((width - tw) / 2, (height - th) / 2)
	else:
		coords = ((width - tw) / 2, position * (height - th))
	draw.text(coords, title, font=image_font, fill=color, align='center')
# EOF
