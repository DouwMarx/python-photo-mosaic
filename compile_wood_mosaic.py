from mosaic import create_mosaic
import pathlib
import yaml
from joblib import Parallel, delayed

tiles_dir = pathlib.Path("/home/douwm/Downloads/wood_mnist/processed/out")
tiles = [p for p in tiles_dir.iterdir() if p.is_file()]# Get all paths of the files in the tiles_dir


# Source images directory
source_directory = pathlib.Path(__file__).parent.joinpath("source_images_processed")

def process(path):
    print("Processing image: {}".format(path.name))
    target_path = pathlib.Path(__file__).parent.joinpath("results", path.name)
    create_mosaic(
        source_path=path,
        target=target_path,
        # target= "./example.jpg", # This directory
        tile_paths=tiles,
        tile_ratio=1,  # Crop tiles to be height/width ratio
        reuse=False,  # Should tiles be used multiple times?
        color_mode='RGB',  # RGB (color) L (greyscale)
        rotate=True,  # Whether to rotate tiles by multiples of 90
        enlargement=2.5,
        tile_width=50
    )

# Loop through all images in source directory
# for path in source_directory.iterdir():
#     process(path)

Parallel(n_jobs=8)(delayed(process)(path) for path in source_directory.iterdir())

