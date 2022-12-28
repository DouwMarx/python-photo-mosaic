# Use pil to resize all the images in the source images directory to have a pixel count of roungly 1000000

import pathlib
import PIL
from PIL import Image
import os

source_directory = pathlib.Path(__file__).parent.joinpath("source_images")
target_directory = pathlib.Path(__file__).parent.joinpath("source_images_processed")

target_pixel_count = 500000
for path in source_directory.iterdir():
    print("Processing image: {}".format(path.name))
    target_path = target_directory.joinpath(path.name)
    im = Image.open(path)
    current_pixel_count = im.size[0] * im.size[1]
    resize_factor = (target_pixel_count/current_pixel_count)**0.5
    new_size = (int(im.size[0]*resize_factor), int(im.size[1]*resize_factor))
    im = im.resize(new_size, PIL.Image.ANTIALIAS)
    im.save(target_path)


