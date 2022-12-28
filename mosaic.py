import pathlib
import time
import itertools
import random
import sys
import re

import numpy as np
from PIL import Image
from matplotlib import patches
from skimage import img_as_float
from skimage.metrics import mean_squared_error as compare_mse
from tqdm import tqdm
import matplotlib.pyplot as plt
import pickle

def shuffle_first_items(lst, i):
    if not i:
        return lst
    first_few = lst[:i]
    remaining = lst[i:]
    random.shuffle(first_few)
    return first_few + remaining

def bound(low, high, value):
    return max(low, min(high, value))

class ProgressCounter:
    def __init__(self, total):
        self.total = total
        self.counter = 0

    def update(self):
        self.counter += 1
        sys.stdout.write("Progress: %s%% %s" % (100 * self.counter / self.total, "\r"))
        sys.stdout.flush()

def resize_box_aspect_crop_to_extent(img, target_aspect, centerpoint=None):
    width = img.size[0]
    height = img.size[1]
    if not centerpoint: # Specifying centerpoint allows focus to be at specific location
        centerpoint = (int(width / 2), int(height / 2))

    requested_target_x = centerpoint[0]
    requested_target_y = centerpoint[1]
    aspect = width / float(height)
    if aspect > target_aspect:
        # Then crop the left and right edges:
        new_width = int(target_aspect * height)
        new_width_half = int(new_width/2)
        target_x = bound(new_width_half, width-new_width_half, requested_target_x)
        left = target_x - new_width_half
        right = target_x + new_width_half
        resize = (left, 0, right, height)
    else:
        # ... crop the top and bottom:
        new_height = int(width / target_aspect)
        new_height_half = int(new_height/2)
        target_y = bound(new_height_half, height-new_height_half, requested_target_y)
        top = target_y - new_height_half
        bottom = target_y + new_height_half
        resize = (0, top, width, bottom)
    return resize

def aspect_crop_to_extent(img, target_aspect, centerpoint=None):
    '''
    Crop an image to the desired perspective at the maximum size available.
    Centerpoint can be provided to focus the crop to one side or another -
    eg just cut the left side off if interested in the right side.

    target_aspect = width / float(height)
    centerpoint = (width, height)
    '''
    resize = resize_box_aspect_crop_to_extent(img, target_aspect, centerpoint)
    return img.crop(resize)

class Config:
    def __init__(self, tile_ratio=1920/800, tile_width=50, match_width = 20, enlargement=8, color_mode='RGB', rotate=False):
        self.tile_ratio = tile_ratio # 2.4
        self.match_width = match_width
        self.tile_width = tile_width # height/width of mosaic tiles in pixels
        self.enlargement = enlargement # mosaic image will be this many times wider and taller than original
        self.color_mode = color_mode # mosaic image will be this many times wider and taller than original
        self.rotate = rotate

    @property
    def tile_height(self):
        return int(self.tile_width / self.tile_ratio)

    @property
    def tile_size(self):
        return self.tile_width, self.tile_height # PIL expects (width, height)

class TileBox:
    """
    Container to import, process, hold, and compare all of the tiles
    we have to make the mosaic with.
    """
    def __init__(self, tile_paths, config):
        self.config = config
        self.tiles = list()
        self.tile_names = list() # Keep track of tile names for building
        self.prepare_tiles_from_paths(tile_paths)

    def __process_tile(self, tile_path):
        with Image.open(tile_path) as i:
            img = i.copy()
        img = aspect_crop_to_extent(img, self.config.tile_ratio)
        large_tile_img = img.resize(self.config.tile_size, Image.ANTIALIAS).convert(self.config.color_mode)
        self.tiles.append(large_tile_img)

        name = tile_path.stem.split('.')[0][-4:]
        self.tile_names.append(name)
        if self.config.rotate:
            # for i in range(3):
            for i, direction in enumerate(["→","↓","←"]): # Plot ascii arrows
                self.tiles.append(large_tile_img.rotate(90 * (1+i))) # TODO: Will this work if images are to be used without replacement?
                self.tile_names.append(name + (f'\nr{90 * (1+i)}' + direction))
        return True

    def prepare_tiles_from_paths(self, tile_paths):
        print('Reading tiles from provided list...')
        #progress = ProgressCounter(len(tile_paths))
        for tile_path in tqdm(tile_paths):
            #progress.update()
            self.__process_tile(tile_path)
        print('Rescaling tiles for matching...')

        match_size = self.config.match_width, int(self.config.match_width / self.config.tile_ratio)

        self.tile_array = np.array([np.array(t.resize(match_size,Image.NEAREST)) for t in self.tiles]).astype("float32")
        print('Processed tiles.')
        return True

    def best_tile_block_match(self, tile_block_original):
        a = np.array(tile_block_original).astype("float32")
        if self.config.color_mode == 'RGB':
            match_results = ((self.tile_array - a.reshape((1,) + a.shape) )**2).mean((1,2,3)) #[img_mse(t, tile_block_original) for t in self.tiles]
        elif self.config.color_mode == 'L':
            match_results = ((self.tile_array - a.reshape((1,) + a.shape) )**2).mean((1,2))
        return match_results.argsort()  # best_fit_tile_index

    # def best_tile_from_block(self, tile_block_original, reuse=False):
    #     if not self.tiles:
    #         print('Ran out of images.')
    #         raise KeyboardInterrupt
    #
    #     #start_time = time.time()
    #     i = self.best_tile_block_match(tile_block_original) # Sorted indexes of images that have the fit criterion
    #
    #     match = self.tiles[i].copy() # Reshuffle according the match criterion and make a copy
    #     if not reuse:
    #         if self.config.rotate:
    #             indeces = [int(i/4)*4 + j for j in range(3,-1,-1)] # remove all rotated copies
    #         else:
    #             indeces = [i]
    #         for j in indeces:
    #             del self.tiles[j]
    #         self.tile_array = np.delete(self.tile_array, indeces, axis=0)
    #     return match

class SourceImage:
    """Processing original image - scaling and cropping as needed."""
    def __init__(self, image_path, config):
        print('Processing main image...')
        self.image_path = image_path
        self.config = config

        with Image.open(self.image_path) as i:
            img = i.copy()
        w = int(img.size[0] * self.config.enlargement)
        h = int(img.size[1]	* self.config.enlargement)
        large_img = img.resize((w, h), Image.ANTIALIAS)
        w_diff = (w % self.config.tile_width)/2
        h_diff = (h % self.config.tile_height)/2

        # if necesary, crop the image slightly so we use a
        # whole number of tiles horizontally and vertically
        if w_diff or h_diff:
            large_img = large_img.crop((w_diff, h_diff, w - w_diff, h - h_diff))

        self.image =  large_img.convert(self.config.color_mode)
        print('Main image processed.')

class MosaicImage:
    """Holder for the mosaic"""
    def __init__(self, original_img, target, config):
        self.config = config
        self.target = target
        # Lets just start with original image, scaled up, instead of a blank one
        self.image = original_img
        # self.image = Image.new(original_img.mode, original_img.size)
        self.x_tile_count = int(original_img.size[0] / self.config.tile_width)
        self.y_tile_count = int(original_img.size[1] / self.config.tile_height)
        self.total_tiles  = self.x_tile_count * self.y_tile_count
        print(f'Mosaic will be {self.x_tile_count:,} tiles wide and {self.y_tile_count:,} tiles high ({self.total_tiles:,} total).')

    def add_tile(self, tile, coords):
        """Adds the provided image onto the mosiac at the provided coords."""
        try:
            self.image.paste(tile, coords)
        except TypeError as e:
            print('Maybe the tiles are not the right size. ' + str(e))

    def save(self):
        self.image.save(self.target)

class BuildInstructions():
    """Instructions for building the mosaic"""
    def __init__(self, config):
        self.names = list()
        self.boxes = list()
        self.config = config

    def show_instructions(self, instruction_path):
        fig, ax = plt.subplots()
        scale = 100

        # Keep only the 4 digit numerical part of the name

        # Show the names in the center of the boxes
        for i, box in enumerate(self.boxes):
            x = box[0] + (box[2] - box[0]) / 2
            y = box[1] + (box[3] - box[1]) / 2
            ax.text(x/scale, y/scale, self.names[i], ha='center', va='center', size=1.6)

        # Show the grid of the boxes
        for box in self.boxes:
            x = np.array([box[0], box[2], box[2], box[0], box[0]])
            y = np.array([box[1], box[1], box[3], box[3], box[1]])
            ax.plot(x/scale, y/scale, color='red', linewidth=0.5)

        # Dont show axes of axis ticks
        ax.set_xticks([])
        ax.set_yticks([])
        ax.axis('off')


        #Save as png
        plt.savefig(instruction_path, dpi=900, bbox_inches='tight')

    def add_tile(self, name, box):
        self.names.append(name)
        self.boxes.append(box)






def coords_from_middle(x_count, y_count, y_bias=1, shuffle_first=0, ):
    '''
    Lets start in the middle where we have more images.
    And we dont get "lines" where the same-best images
    get used at the start.

    y_bias - if we are using non-square coords, we can
        influence the order to be closer to the real middle.
        If width is 2x height, y_bias should be 2.

    shuffle_first - We can suffle the first X coords
        so that we dont use all the same-best images
        in the same spot -  in the middle

    from movies.mosaic_mem import coords_from_middle
    x = 10
    y = 10
    coords_from_middle(x, y, y_bias=2, shuffle_first=0)
    '''
    x_mid = int(x_count/2)
    y_mid = int(y_count/2)
    coords = list(itertools.product(range(x_count), range(y_count)))
    coords.sort(key=lambda c: abs(c[0]-x_mid)*y_bias + abs(c[1]-y_mid))
    coords = shuffle_first_items(coords, shuffle_first)
    return coords


def create_mosaic(source_path, target, tile_ratio=1920/800, tile_width=75, match_width=20, enlargement=8, reuse=True, color_mode='RGB', tile_paths=None, shuffle_first=30, rotate=False):
    """Forms an mosiac from an original image using the best
    tiles provided. This reads, processes, and keeps in memory
    a copy of the source image, and all the tiles while processing.

    Arguments:
    source_path -- filepath to the source image for the mosiac
    target -- filepath to save the mosiac
    tile_ratio -- height/width of mosaic tiles in pixels
    tile_width -- width of mosaic tiles in pixels (Image tile is resized)
    enlargement -- mosaic image will be this many times wider and taller than the original
    reuse -- Should we reuse tiles in the mosaic, or just use each tile once?
    color_mode -- L for greyscale or RGB for color
    tile_paths -- List of filepaths to your tiles
    shuffle_first -- Mosiac will be filled out starting in the center for best effect. Also,
        we will shuffle the order of assessment so that all of our best images aren't
        necessarily in one spot.
    rotate -- Rotate images to check for better matches in rotated version
    match_width -- Resolution at which the tiles are compared to the source image.
    """
    config = Config(
        tile_ratio = tile_ratio,		# height/width of mosaic tiles in pixels
        tile_width = tile_width,		# height/width of mosaic tiles in pixels
        enlargement = enlargement,	    # the mosaic image will be this many times wider and taller than the original
        color_mode = color_mode,	    # L for greyscale or RGB for color
        rotate = rotate,
        match_width=match_width,
    )
    # Pull in and Process Original Image
    print('Setting Up Target image')
    source_image = SourceImage(source_path, config)

    # Setup Mosaic
    mosaic = MosaicImage(source_image.image, target, config)
    build_instructions = BuildInstructions(config)

    # Assest Tiles, and save if needed, returns directories where the small and large pictures are stored
    print('Assessing Tiles')
    tile_box = TileBox(tile_paths, config)
    # # Save as pickle for quick loading later
    # with open('tile_box.pkl', 'wb') as f:
    #     pickle.dump(tile_box, f)
    # # Load from pickle
    # with open('tile_box.pkl', 'rb') as f:
    #     tile_box = pickle.load(f)

    matches = list()
    boxes = list()
    print("Matching tiles..\n")

    for x, y in tqdm(coords_from_middle(mosaic.x_tile_count, mosaic.y_tile_count, y_bias=config.tile_ratio, shuffle_first=shuffle_first)):
        # Make a box for this sector
        box_crop = (x * config.tile_width, y * config.tile_height, (x + 1) * config.tile_width, (y + 1) * config.tile_height)

        # Get Original Image Data for this Sector
        comparison_block = source_image.image.crop(box_crop).resize([config.match_width, int(config.match_width/config.tile_ratio)])

        # Get Best Image name that matches the Orig Sector image
        matches.append(tile_box.best_tile_block_match(comparison_block)) # Ranking of how well a tile would work for a region in the original image
        boxes.append(box_crop) # The box in the original image that we are trying to fill with a tile
        #tile_match = tile_box.best_tile_from_block(comparison_block, reuse=reuse)

    print("Assembling mosaic..\n")
    available = set([i for i in range(len(tile_box.tiles))])
    
    try:
        for i, m in enumerate(tqdm(matches)): # Loop though the locations in the original image (each having a ranking asking for a given tile)

            if not available:
                print("Ran out of tiles!\n")
                mosaic.save()
                break
            
            if not reuse:
                j = next(j for j in m if j in available) # m is a ranking of how well a tile would work for a region in the original image
                if config.rotate:
                    indeces = [int(j/4)*4 + k for k in range(3,-1,-1)] # remove all rotated copies
                else:
                    indeces = [j]
                #for k in indeces:
                #    del available[available.index(k)]
                available = available - set(indeces)
            else:
                j = m[0]
            tile = tile_box.tiles[j].copy()
            tile_name = tile_box.tile_names[j]
            
            # Add Best Match to Mosaic
            mosaic.add_tile(tile, boxes[i])
            build_instructions.add_tile(tile_name, boxes[i])

            # Saving Every Sector
            #if i % 100 == 99: 
            #    mosaic.save() 

    except KeyboardInterrupt:
        print('\nStopping, saving partial image...')

    finally:
        mosaic.save()
    
    mosaic.save()
    build_instructions.show_instructions(pathlib.Path(__file__).parent.joinpath("instructions", source_path.stem))
