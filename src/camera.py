from OpenGL.GLUT import *
from OpenGL.GLU import *
from OpenGL.GL import *
import numpy as np
import glm
from math import sin, cos, pi

#todo: allow the cursor to be accessible when the GUI is activated
class Camera():
    def __init__(self, fov, aspect) -> None:
        self.position = glm.vec3(0.0, 2.0, 0.0) #camera begins 1 unit away from origin
        self.target = glm.vec3(0.0, 0.0, 0.0) #origin
        #get view direction (towards origin)
        self.forward = glm.normalize(self.target - self.position)
        #right direction is cross product of world up and view direction
        self.right = glm.normalize(glm.cross(glm.vec3(0.0, 0.0, 1.0), self.forward))
        #camera up is cross product of view direction and right direction
        self.up = glm.normalize(glm.cross(self.forward, self.right))
        self.fov = fov
        self.aspect = aspect

        self.zoom_factor = 0.5
        self.ortho_width = 2.0 / self.zoom_factor
        self.ortho_height = (self.ortho_width / self.aspect)

        self.movement_speed = 0.5

        self.pitch = 0.0
        self.yaw = 0.0


    def set_uniforms(self, program) -> None:
        #camera projection and view
        matrix = [x for y in self._get_projection() for x in y]
        glUniformMatrix4fv(glGetUniformLocation(program, "projection"), 1, GL_FALSE, matrix)
        matrix = [x for y in self._get_view() for x in y]
        glUniformMatrix4fv(glGetUniformLocation(program, "view"), 1, GL_FALSE, matrix)

    #rotate the camera around the origin
    def rotate_origin(self, delta_x, delta_y):
        radius = glm.length(self.position)
        x_angle = delta_x * (pi / 2.0)
        y_angle = delta_y * (pi / 2.0)

        self.yaw -= x_angle
        self.pitch += y_angle #screen coordinates are flipped

        #limit pitch to prevent over rotation
        if (self.pitch > pi / 2.0):
            self.pitch = pi / 2.0
        if (self.pitch < -pi / 2.0):
            self.pitch = -pi / 2.0

        self.position = glm.vec3(radius * cos(self.yaw) * cos(self.pitch), radius * sin(self.yaw) * cos(self.pitch), radius * sin(self.pitch))
        self.forward = glm.normalize(-self.position)

    def rotate(self, delta_x, delta_y):
        x_angle = delta_x * (pi / 2.0)
        y_angle = delta_y * (pi / 2.0)
        
        #rotate around axes
        self.yaw -= x_angle
        self.pitch -= y_angle #screen coordinates are flipped

        #limit pitch to prevent over rotation
        if (self.pitch > pi / 2.0):
            self.pitch = pi / 2.0
        if (self.pitch < -pi / 2.0):
            self.pitch = -pi / 2.0

        direction = glm.vec3()
        direction.x = cos(self.yaw) * cos(self.pitch)
        direction.y = sin(self.yaw) * cos(self.pitch)
        direction.z = sin(self.pitch)

        self.forward = glm.normalize(direction)
        self.right = glm.normalize(glm.cross(glm.vec3(0.0, 0.0, 1.0), self.forward))
        self.up = glm.normalize(glm.cross(self.forward, self.right))

    def adjust_zoom(self, delta):
        self.zoom_factor += delta
        self.ortho_width = 1.0 / self.zoom_factor
        self.ortho_height = (self.ortho_width / self.aspect)

    def _get_view(self) -> glm.mat4:
        return glm.lookAt(self.position, self.position + self.forward, self.up)
    
    def _get_projection(self) -> glm.mat4:
        #orthographic camera
        return glm.ortho(-self.ortho_width / 2.0, self.ortho_width / 2.0, -self.ortho_height / 2.0, self.ortho_height / 2.0, 0.1, 10.0)
        #return glm.orth  #glm.perspective(self.fov, self.aspect, 0.1, 100.0)
    
