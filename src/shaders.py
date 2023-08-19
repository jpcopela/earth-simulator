from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import numpy as np

class Shader():
    def __init__(self, shader_kwargs=None) -> None:
        self.shader_kwargs = shader_kwargs
        self.shaders = []

    def load(self) -> None:
        self.program = glCreateProgram()
        
        #compile and attach each shader in the list
        for shader_obj in self.shader_kwargs:
            shader_type = shader_obj["type"]
            shader_filepath = shader_obj["filepath"]
            shader_src = self._read_shader(shader_filepath)
            shader = self._compile_shader(shader_type, shader_src)
            glAttachShader(self.program, shader)
            self.shaders.append(shader)
    
        glLinkProgram(self.program)

        if glGetProgramiv(self.program, GL_LINK_STATUS) != GL_TRUE:
            raise RuntimeError(glGetProgramInfoLog(self.program))
        
        for shader in self.shaders:
            glDetachShader(self.program, shader)
            glDeleteShader(shader)

    #read the shader source file into an array of strings
    def _read_shader(self, shader_filepath) -> str:
        with open(shader_filepath, 'r') as f:
            shader_str = f.read()

        return shader_str

    def _compile_shader(self, shader_type, shader_src) -> GLuint:
        shader = glCreateShader(shader_type)
        glShaderSource(shader, shader_src)
        glCompileShader(shader)

        if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
            raise RuntimeError(glGetShaderInfoLog(shader))
        
        return shader

    def delete(self) -> None:
        glDeleteProgram(self.program)