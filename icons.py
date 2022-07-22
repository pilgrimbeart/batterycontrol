import pygame
import glob
import os

DIRECTORY = "images/"
ICON_SIZE = 24
IMAGES = {}

os.chdir(os.path.dirname(__file__)) # Change directory to whereever this file is (e.g. if we're run from init script)

def draw_image(surface, imagename, x, y):
    surface.blit(IMAGES[imagename+".png"], (x, y))

def load_images():
    global IMAGES

    for filename in os.listdir(DIRECTORY):
        f = os.path.join(DIRECTORY, filename)
        i = pygame.image.load(f) # The "libpng warning: iCCP: known incorrect sRGB profile" can safely be ignored, it's from a chunk which isn't used
        i = pygame.transform.smoothscale(i, (ICON_SIZE, ICON_SIZE))
        IMAGES[filename] = i


if __name__ == "__main__":
    load_images()
    print(IMAGES)
