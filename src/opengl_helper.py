from OpenGL.GL import *
from OpenGL.GLU import *

from src.shaders import Shader
from src.camera import Camera
from src.objects import Object

import numpy as np
import matplotlib.pyplot as plt

from PIL import Image

#this cleans up the code in my GLWidget class and allows
#the widgets to load faster. The user then specifies the objects and images they want to load

class GLInstance():
    shader_kwargs = [{'type': GL_VERTEX_SHADER, 'filepath': 'shaders/vertex.glsl'},
                    {'type': GL_FRAGMENT_SHADER, 'filepath': 'shaders/fragment.glsl'}]
    
    def __init__(self, w : int, h : int) -> None:
        self.w = w
        self.h = h

        self.shaders = Shader(self.shader_kwargs)
        self.camera = Camera(45.0, self.w / self.h)
        self.satellites = {}

    def load_satellite(self, satellite : str) -> None:
        object = Object(satellite)
        self.satellites[satellite] = object

    def remove_satellite(self, satellite : str) -> None:
        try:
            self.satellites.pop(satellite)
        except:
            print(f'Object {satellite} is not loaded.')
            pass

    def load_texture_images(self, satellite : str, images : list) -> None:
        self.satellites[satellite].load_textures(images)

    #remove the active texture images
    def remove_texture_images(self, satellite : str) -> None:
        self.satellites[satellite].clear_images()

