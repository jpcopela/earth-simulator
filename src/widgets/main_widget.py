import wx
from src.widgets.gl_widget import OpenGLCanvas
from src.widgets.sidebar_widget import SidebarWidget
from src.widgets.misc_widgets import BottomBar, CapturedOutput, ConfirmationDialog, AttemptFixWorker
from src.diagnostics import AppDiagnostics

import sys

class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, title=title, size=(800, 600))
        self.queries = []
        self.query_response_counter = 0

        #create our vertical and horizontal splitters to divide into 3 sections
        self.splitter_vertical = wx.SplitterWindow(self)
        self.splitter_horizontal = wx.SplitterWindow(self.splitter_vertical)

        #initialize our widgets
        self.bottom_bar = BottomBar(self.splitter_horizontal)
        #initialize a custom stream object to capture output and display it on the bottom bar
        self.captured_output = CapturedOutput(self.bottom_bar.text_ctrl)
        self.opengl_canvas = OpenGLCanvas(self.splitter_horizontal, self.captured_output)
        self.sidebar = SidebarWidget(self.splitter_vertical, self.captured_output)

        #set the initial sash positions
        self.splitter_horizontal.SplitHorizontally(self.opengl_canvas, self.bottom_bar)
        self.set_horizontal_sash_position(0.8)
        self.splitter_vertical.SplitVertically(self.splitter_horizontal, self.sidebar)
        self.set_vertical_sash_position(0.75)

        #bind events required for opengl and main window
        self.Bind(wx.EVT_SIZE, self.on_splitter_resize)
        self.sidebar.Bind(SidebarWidget.EVT_SATELLITE_TOGGLE, self.on_satellite_toggle)
        self.sidebar.Bind(SidebarWidget.EVT_IMAGE_SELECTION, self.on_images_selected)
        self.sidebar.Bind(SidebarWidget.EVT_SLIDER_CHANGE, self.on_slider_value_changed)
        self.sidebar.Bind(SidebarWidget.EVT_TIMELAPSE_CLICK, self.on_timelapse_click)

        self.Centre()
        self.Show()

        sys.stdout = self.captured_output #redirect stdout to our custom stream object
        sys.stderr = self.captured_output #redirect stderr to our custom stream object

        self.file_status = AppDiagnostics(resolutions=['low_res', 'medium_res', 'high_res'])
        self.file_status.run_diagnotics()
        
        if (self.file_status.missing_resolutions != []):
            for res in self.file_status.missing_resolutions:
                dlg = ConfirmationDialog(self, res)
                result = dlg.ShowModal()
                dlg.Destroy()

                if result == wx.ID_YES:
                    thread = AttemptFixWorker(self, res)
                    thread.start()

    def set_horizontal_sash_position(self, proportion):
        _, window_height = self.GetSize()
        self.splitter_horizontal.SetSashPosition(int(window_height * proportion))

    def set_vertical_sash_position(self, proportion):
        window_width, _ = self.GetSize()
        self.splitter_vertical.SetSashPosition(int(window_width * proportion))

    def on_splitter_resize(self, event):
        self.set_horizontal_sash_position(0.8)  # Adjust sash position when window size changes
        self.set_vertical_sash_position(0.75)
        event.Skip()

    #when a new satellite is selected
    def on_satellite_toggle(self, event):
        satellite = event.satellite
        selected = event.selected
        self.opengl_canvas.handle_satellite_toggle(satellite, selected)

    #when new images are selected
    def on_images_selected(self, event):
        satellite = event.satellite
        images = event.files
        self.opengl_canvas.handle_images_selected(satellite, images)

    #when the timeline slider changes
    def on_slider_value_changed(self, event):
        value = event.value
        self.opengl_canvas.handle_slider_value_changed(value)

    def on_timelapse_click(self, event):
        satellites = event.satellites
        folder = event.folder
        resolution = event.resolution
        self.opengl_canvas.handle_timelapse_click(satellites, folder, resolution)

    def on_blend_image_click(self, event):
        blend_images = event.blend_images

        self.opengl_canvas.handle_blend_toggle(blend_images)
