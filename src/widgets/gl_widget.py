import wx
from wx import glcanvas
from OpenGL.GL import *
from src.opengl_helper import GLInstance  # Replace with your OpenGL helper class
import time

import sys

import numpy as np

from glob import glob
from datetime import datetime

#the canvas that will be used to display the OpenGL scene
class OpenGLCanvas(glcanvas.GLCanvas):
    def __init__(self, parent, captured_output=None):
        attribs = (wx.glcanvas.WX_GL_RGBA, wx.glcanvas.WX_GL_DOUBLEBUFFER, wx.glcanvas.WX_GL_DEPTH_SIZE, 24)
        style = wx.WANTS_CHARS | wx.NO_FULL_REPAINT_ON_RESIZE
        super(OpenGLCanvas, self).__init__(parent, attribList=attribs, style=style)

        self.width = self.GetClientSize()[0]
        self.height = self.GetClientSize()[1]

        sys.stdout = captured_output
        sys.stderr = captured_output

        self.context = wx.glcanvas.GLContext(self)
        self.gl_initialized = False

        self.slider_value = 0 #the initial value of the slider
        self.movement_keys = {'W': False, 'S': False, 'A': False, 'D': False} #the keys that will be used to move the camera

        #used for animating the textures
        self.elapsed = 0.0
        self.prev = 0.0
        self.delta = 0.0

        self.timelapse_counter = 0

        #used for rotating the camera
        self.last_mouse_pos = None
        self.mouse_clicked = False

        self.timer = wx.Timer(self)

        #bind the events
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_KEY_UP, self._on_key_up)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mouse_wheel)
        self.Bind(wx.EVT_MOTION, self._on_mouse_move)
        self.Bind(wx.EVT_SIZE, self._on_resize)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_TIMER, self._on_timer)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self.timer.Start(16)  # 60 FPS

    #methods for handling events passed by the main window from the sidebar
    def handle_satellite_toggle(self, satellite, checked):
        #if the satellite is checked, load it, otherwise remove it
        if checked:
            self.gl.load_satellite(satellite)
            self.objects = self.gl.satellites
        else:
            self.gl.remove_satellite(satellite)
            self.objects = self.gl.satellites

    def handle_images_selected(self, satellite, images):
        self.gl.remove_texture_images(satellite)
        self.gl.load_texture_images(satellite, images)

    def handle_slider_value_changed(self, value : int):
        self.slider_value = value

    def handle_timelapse_click(self, satellites, project_folder, resolution):
        print('Creating timelapse...')
        #calculate image pairs based on timestamps
        timestamp_format = '%Y%m%d_%H%M'
        image_files = []

        for satellite in satellites:
            path = project_folder + f'/images/{satellite}/{resolution}/'
            images = glob(path + '*.png')
            image_files.extend(images)

        timestamps = []

        for file in image_files:
            date_str = file.split('_')[-2:]
            date_str = str(date_str[0] + '_' + date_str[1]).split('.')[0]
            date = datetime.strptime(date_str, timestamp_format)
            timestamps.append(date)
        
        timestamps = sorted(timestamps) #sort the timestamps and convert them to a string so we can sort the image files
        ts_str = [date.strftime(timestamp_format) for date in timestamps]
        ts_str = list(dict.fromkeys(ts_str)) #remove duplicates
        image_groups = []

        for timestamp in ts_str:
            group = [i for i in image_files if timestamp in i]
            image_groups.append(tuple(group))

        self.SetCurrent(self.context)
        for i in range(len(image_groups)):
            for image in image_groups[i]:
                for satellite in satellites:
                    if satellite in image:
                        self.gl.remove_texture_images(satellite)
                        self.gl.load_texture_images(satellite, [image])
                    
            self.paintGL()
            self.gl.capture_image(self.width, self.height, self.timelapse_counter, i, project_folder)

        self.timelapse_counter += 1

    #methods for interacting with the OpenGL scene
    def _on_key_down(self, event):
        keycode = event.GetKeyCode()

        if keycode == ord('W') or keycode == ord('w'):
            self.movement_keys['W'] = True
        elif keycode == ord('A') or keycode == ord('a'):
            self.movement_keys['A'] = True
        elif keycode == ord('S') or keycode == ord('s'):
            self.movement_keys['S'] = True
        elif keycode == ord('D') or keycode == ord('d'):
            self.movement_keys['D'] = True
        
        event.Skip()
    
    def _on_key_up(self, event):
        keycode = event.GetKeyCode()
        
        if keycode == ord('W') or keycode == ord('w'):
            self.movement_keys['W'] = False
        elif keycode == ord('A') or keycode == ord('a'):
            self.movement_keys['A'] = False
        elif keycode == ord('S') or keycode == ord('s'):
            self.movement_keys['S'] = False
        elif keycode == ord('D') or keycode == ord('d'):
            self.movement_keys['D'] = False

        event.Skip()

    def _on_left_down(self, event):
        #setting the focus is important
        self.mouse_clicked = True
        self.SetFocus()

    def _on_left_up(self, event):
        self.mouse_clicked = False

    def _on_mouse_wheel(self, event) -> None:
        #zoom the camera in and out
        delta = event.GetWheelRotation() / (event.GetWheelDelta() * 100)
        self.camera.adjust_zoom(delta) # Adjust the zoom speed as needed

        self.Refresh()

    def _on_mouse_move(self, event):
        if not self.mouse_clicked:
            self.last_mouse_pos = None

        if self.mouse_clicked:
            width, height = self.GetClientSize()

            x, y = event.GetX(), event.GetY()

            if self.last_mouse_pos is None:
                self.last_mouse_pos = wx.Point(x, y)

            delta_x = (x - self.last_mouse_pos.x) / width
            delta_y = (y - self.last_mouse_pos.y) / height

            self.last_mouse_pos = wx.Point(x, y)
            self.camera.rotate_origin(delta_x, delta_y)
        
    def _on_resize(self, event):
        if not self.gl_initialized:
            self.initializeGL()
            self.gl_initialized = True

        width, height = self.GetClientSize()
        self.SetCurrent(self.context)
        glViewport(0, 0, width, height)

        self.camera.aspect = width / height
        self.camera.adjust_zoom(0.0)

        self.width = width
        self.height = height

    def _on_paint(self, event):
        dc = wx.PaintDC(self)
        self.SetCurrent(self.context)

        if not self.gl_initialized:
            self.initializeGL()
            self.gl_initialized = True

        self.paintGL()
        self.SwapBuffers()

    def _on_timer(self, event):
        self._move_camera()
        self.Refresh()

    def _on_close(self, event):
        self.timer.Stop()
        self.SetCurrent(self.context)
        [glDeleteShader(shader) for shader in self.shaders.shaders]
        [glDeleteProgram(shader) for shader in self.shaders.program]

        for satellite in self.objects:
            self.gl.remove_satellite(satellite)
            self.gl.remove_texture_images(satellite)

        event.Skip()

    def _move_camera(self):
        if self.movement_keys['W']:
            self.camera.position += self.camera.forward * self.camera.movement_speed * self.delta
        if self.movement_keys['S']:
            self.camera.position -= self.camera.forward * self.camera.movement_speed * self.delta
        if self.movement_keys['A']:
            self.camera.position += self.camera.right * self.camera.movement_speed * self.delta
        if self.movement_keys['D']:
            self.camera.position -= self.camera.right * self.camera.movement_speed * self.delta

    def initializeGL(self):
        #initialize OpenGL
        self.SetCurrent(self.context)

        glClearColor(0.0725, 0.025, 0.05, 1.0)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)
        glDisable(GL_CULL_FACE)

        #initialize the OpenGL helper class objects
        self.gl = GLInstance(self.GetSize()[0], self.GetSize()[1])
        self.shaders = self.gl.shaders
        self.camera = self.gl.camera
        self.objects = self.gl.satellites
        self.shaders.load()

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        #update the time
        current = time.time()
        self.delta = current - self.prev
        self.elapsed += self.delta
        self.prev = current

        if self.elapsed > 1.0:
            self.elapsed = 0.0

        #for each tile in each satellite, draw the tile with appropriate timeseries index
        for satellite in self.objects:
            for i in range(len(self.objects[satellite].textures[self.slider_value])):
                    glBindVertexArray(self.objects[satellite].vao)

                    glBindBuffer(GL_ARRAY_BUFFER, self.objects[satellite].tbos[i])
                    glEnableVertexAttribArray(1)
                    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 0, None)

                    glUseProgram(self.shaders.program)
                    self.camera.set_uniforms(self.shaders.program)

                    glUniform1f(glGetUniformLocation(self.shaders.program, "time"), self.elapsed)
                    glUniform1i(glGetUniformLocation(self.shaders.program, "numLayers"), self.objects[satellite].num_layers)
                    glUniform1i(glGetUniformLocation(self.shaders.program, "image"), 0)

                    glActiveTexture(GL_TEXTURE0)
                    glBindTexture(GL_TEXTURE_2D, self.objects[satellite].textures[self.slider_value][i])

                    glDrawElements(GL_TRIANGLES, self.objects[satellite].length, GL_UNSIGNED_INT, None)

        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glUseProgram(0)