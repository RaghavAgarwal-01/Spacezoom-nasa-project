from PIL import Image
import os

Image.MAX_IMAGE_PIXELS = None

# Only change this variable to process a different image!
IMAGE_TO_TILE = 'backend-api/images/land_shallow_topo_east.tif'
TILE_SIZE = 256

def generate_tiles(image_path, tile_size=TILE_SIZE):
    img = Image.open(image_path)
    img_name = os.path.splitext(os.path.basename(image_path))[0]
    out_dir = f"tiles/{img_name}"
    os.makedirs(out_dir, exist_ok=True)
    width, height = img.size
    for x in range(0, width, tile_size):
        for y in range(0, height, tile_size):
            box = (x, y, min(x + tile_size, width), min(y + tile_size, height))
            tile = img.crop(box)
            tile_filename = f"{img_name}_tile_{x}_{y}.jpg"
            tile.save(os.path.join(out_dir, tile_filename))

if __name__ == "__main__":
    generate_tiles(IMAGE_TO_TILE)
