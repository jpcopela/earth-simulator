import wx
from wx import adv
from datetime import datetime, timezone

import os
from src.download_manager import DownloadManager
from src.data_processor import ImageProcessor
from src.composite_helper import CompositeHelper

from threading import Thread, Lock
import sys

#worker thread for downloading data
class DownloadWorker(Thread):
    def __init__(self, parent, download_manager : DownloadManager, project_folder):
        Thread.__init__(self)
        self.lock = Lock()
        self.parent = parent
        self.running = False
        self.download_manager = download_manager
        self.project_folder = project_folder

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        with self.lock: #not really sure if this is necessary
            self.download_manager.download_data(self.project_folder)

#worker thread for processing images
class ProcessorWorker(Thread):
    def __init__(self, image_processor : ImageProcessor):
        Thread.__init__(self)
        self.lock = Lock()
        self.running = False
        self.image_processor = image_processor

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        with self.lock:
           self.image_processor.process_images()

#custom events
class SatelliteToggleEvent(wx.PyCommandEvent):
    def __init__(self, evtType, satellite : str, selected : bool, id=wx.ID_ANY):
        super().__init__(evtType, id)
        self.satellite = satellite
        self.selected = selected

class ImageSelectionEvent(wx.PyCommandEvent):
    def __init__(self, evtType, satellite : str, files : list, id=wx.ID_ANY):
        super().__init__(evtType, id)
        self.satellite = satellite
        self.files = files

class TimelapseClickEvent(wx.PyCommandEvent):
    def __init__(self, evtType, satellites : list, folder : str, resolution : str, id=wx.ID_ANY):
        super().__init__(evtType, id)
        self.satellites = satellites
        self.folder = folder
        self.resolution = resolution
        
class SliderChangeEvent(wx.PyCommandEvent):
    def __init__(self, evtType, value : int, id=wx.ID_ANY):
        super().__init__(evtType, id)
        self.value = value


#widget for the sidebar
class SidebarWidget(wx.Panel):
    #initialize events to be used by the OpenGL canvas
    myEVT_SATELLITE_TOGGLE = wx.NewEventType()
    EVT_SATELLITE_TOGGLE = wx.PyEventBinder(myEVT_SATELLITE_TOGGLE, 1)

    myEVT_IMAGE_SELECTION = wx.NewEventType()
    EVT_IMAGE_SELECTION = wx.PyEventBinder(myEVT_IMAGE_SELECTION, 1)

    myEVT_TIMELAPSE_CLICK = wx.NewEventType()
    EVT_TIMELAPSE_CLICK = wx.PyEventBinder(myEVT_TIMELAPSE_CLICK, 1)

    myEVT_SLIDER_CHANGE = wx.NewEventType()
    EVT_SLIDER_CHANGE = wx.PyEventBinder(myEVT_SLIDER_CHANGE, 1)

    def __init__(self, parent, captured_output):
        wx.Panel.__init__(self, parent)

        #redirect stdout to the captured_output object
        sys.stdout = captured_output
        sys.stderr = captured_output
        self.captured_output = captured_output

        self.composite_helpers = {
            "GOES-16": CompositeHelper('satpy_configs/composites/abi.yaml'),
            "GOES-18": CompositeHelper('satpy_configs/composites/abi.yaml'),
            "Himawari-9": CompositeHelper('satpy_configs/composites/ahi.yaml'),
            "Meteosat-9": CompositeHelper('satpy_configs/composites/seviri.yaml'),
            "Meteosat-10": CompositeHelper('satpy_configs/composites/seviri.yaml'),
        }
        
        #initialize important variables
        self.satellite_composites = {
            "GOES-16": CompositeHelper('satpy_configs/composites/abi.yaml').get_available_composites(),
            "GOES-18": CompositeHelper('satpy_configs/composites/abi.yaml').get_available_composites(),
            "Himawari-9": CompositeHelper('satpy_configs/composites/ahi.yaml').get_available_composites(),
            "Meteosat-9": CompositeHelper('satpy_configs/composites/seviri.yaml').get_available_composites(),
            "Meteosat-10": CompositeHelper('satpy_configs/composites/seviri.yaml').get_available_composites(),
        }

        self.selected_satellites = []
        self.selected_composites = {}
        self.selected_images = {}
        self.blend_images = True

        #initialize button/toggle variables
        self.interval_unit_idx = 0
        self.satellite_toggles = {}
        self.file_select_buttons = {}

        #initialize the UI elements
        self.init_ui()

    def init_ui(self):
        #the UI is divided into a top and bottom box corresponding to
        #the view manager and image manager, respectively
        top_box = wx.BoxSizer(wx.VERTICAL)
        top_box_title = wx.StaticText(self, label="View Manager:")
        top_box_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        top_box.Add(top_box_title, flag=wx.EXPAND|wx.ALL, border=5)

        #each toggle has an associated image selection button separated by a spacer
        for satellite in self.satellite_composites:
            satellite_sizer = wx.BoxSizer(wx.HORIZONTAL)
            toggle = wx.CheckBox(self, label=satellite)
            folder_button = wx.Button(self, label="Select Folder")
            satellite_sizer.Add(toggle, flag=wx.EXPAND|wx.ALL, border=2)
            satellite_sizer.AddStretchSpacer()
            satellite_sizer.Add(folder_button, flag=wx.EXPAND|wx.ALL, border=2)
            satellite_sizer.AddSpacer(10)
            top_box.Add(satellite_sizer, flag=wx.EXPAND)

            toggle.Bind(wx.EVT_CHECKBOX, lambda event, satellite=satellite: self.on_satellite_toggle(event, satellite))
            folder_button.Bind(wx.EVT_BUTTON, lambda event, satellite=satellite: self.on_folder_select(event, satellite))

            folder_button.Disable()

            self.satellite_toggles[satellite] = toggle
            self.file_select_buttons[satellite] = folder_button

        #slider for the timeline
        slider_sizer = wx.BoxSizer(wx.HORIZONTAL)
        slider_label = wx.StaticText(self, label="Timeline:")
        self.slider = wx.Slider(self, value=0, minValue=0, maxValue=0)
        self.slider.Bind(wx.EVT_SCROLL, self.on_slider_change)
        timelapse_button = wx.Button(self, label="Create Timelapse")
        timelapse_button.Bind(wx.EVT_BUTTON, self.on_timelapse_click)
        slider_sizer.Add(slider_label, flag=wx.EXPAND|wx.ALL, border=10)
        slider_sizer.Add(self.slider, flag=wx.EXPAND|wx.ALL, border=0)
        slider_sizer.Add(timelapse_button, flag=wx.EXPAND|wx.ALL, border=2)

        top_box.Add(slider_sizer, flag=wx.EXPAND|wx.ALL, border=10)

        #bottom box for the image manager
        bottom_box = wx.BoxSizer(wx.VERTICAL)
        bottom_box.AddSpacer(10)
        bottom_box_title = wx.StaticText(self, label="Image Manager:")
        bottom_box_title.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        bottom_box.Add(bottom_box_title, flag=wx.EXPAND|wx.ALL, border=5)

        #satellite combo box
        satellite_label = wx.StaticText(self, label="Select Satellite:")
        self.satellite_combo = wx.ComboBox(self, choices=self.selected_satellites, style=wx.CB_READONLY)
        self.satellite_combo.Bind(wx.EVT_COMBOBOX, self.on_satellite_combo_change)

        bottom_box.Add(satellite_label, flag=wx.EXPAND|wx.ALL, border=2)
        bottom_box.Add(self.satellite_combo, flag=wx.EXPAND|wx.ALL, border=2)

        # Composite Selection Dropdown
        composite_label = wx.StaticText(self, label="Select Composites:")
        self.displayed_composites = wx.CheckListBox(self, choices=[], style=wx.LB_MULTIPLE)
        self.displayed_composites.Bind(wx.EVT_CHECKLISTBOX, self.on_composite_checkbox_change)

        bottom_box.Add(composite_label, flag=wx.EXPAND|wx.ALL, border=2)
        bottom_box.Add(self.displayed_composites, flag=wx.EXPAND|wx.ALL, border=2)

        #date and Interval Selection
        utc_now = datetime.now(timezone.utc)

        #convert to wx
        utc_date_wx = wx.DateTime(year=utc_now.year, month=utc_now.month - 1, day=utc_now.day, hour=utc_now.hour, minute=utc_now.minute, second=utc_now.second)
        utc_time_wx = wx.DateTime.Now()
        utc_time_wx.SetHour(utc_now.hour)
        utc_time_wx.SetMinute(utc_now.minute)
        utc_time_wx.SetSecond(utc_now.second)

        #start time
        start_datetime_sizer = wx.BoxSizer(wx.HORIZONTAL)
        start_datetime_label = wx.StaticText(self, label="Start Date:")
        self.start_datetime_edit = wx.adv.GenericDatePickerCtrl(self, dt=utc_date_wx)
        self.start_time_edit = wx.adv.TimePickerCtrl(self, style=wx.adv.DP_SPIN, dt=utc_time_wx)

        start_datetime_sizer.Add(start_datetime_label, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        start_datetime_sizer.AddStretchSpacer()
        start_datetime_sizer.Add(self.start_datetime_edit, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        start_datetime_sizer.Add(self.start_time_edit, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        start_datetime_sizer.AddSpacer(8)

        #end time
        end_datetime_sizer = wx.BoxSizer(wx.HORIZONTAL)
        end_datetime_label = wx.StaticText(self, label="End Date:")
        self.end_datetime_edit = wx.adv.GenericDatePickerCtrl(self, dt=utc_date_wx)
        self.end_time_edit = wx.adv.TimePickerCtrl(self, style=wx.adv.DP_SPIN, dt=utc_time_wx)

        end_datetime_sizer.Add(end_datetime_label, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        end_datetime_sizer.AddStretchSpacer()
        end_datetime_sizer.Add(self.end_datetime_edit, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        end_datetime_sizer.Add(self.end_time_edit, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        end_datetime_sizer.AddSpacer(8)

        bottom_box.Add(start_datetime_sizer, flag=wx.EXPAND|wx.ALL, border=5)
        bottom_box.Add(end_datetime_sizer, flag=wx.EXPAND|wx.ALL, border=5)

        #initialize the start_time, end_time, and interval variables
        wx_start_date = self.start_datetime_edit.GetValue()
        wx_start_time = self.start_time_edit.GetValue()
        self.start_time = datetime(year=wx_start_date.GetYear(), month=wx_start_date.GetMonth() + 1, day=wx_start_date.GetDay(),
                                   hour=wx_start_time.GetHour(), minute=wx_start_time.GetMinute(), second=wx_start_time.GetSecond())

        wx_end_date = self.end_datetime_edit.GetValue()
        wx_end_time = self.end_time_edit.GetValue()
        self.end_time = datetime(year=wx_end_date.GetYear(), month=wx_end_date.GetMonth() + 1, day=wx_end_date.GetDay(),
                                 hour=wx_end_time.GetHour(), minute=wx_end_time.GetMinute(), second=wx_end_time.GetSecond())

        interval_sizer = wx.BoxSizer(wx.HORIZONTAL)

        interval_label = wx.StaticText(self, label="Interval:")
        self.interval_spinbox = wx.SpinCtrl(self, value="1", min=1, max=1440)
        self.interval_spinbox.Bind(wx.EVT_SPINCTRL, self.on_interval_change)

        interval_unit_button = wx.Button(self, label="Minutes")
        interval_unit_button.Bind(wx.EVT_BUTTON, self.on_interval_unit_click)

        interval_sizer.Add(interval_label, flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=2)
        interval_sizer.AddStretchSpacer()
        interval_sizer.Add(self.interval_spinbox, flag=wx.EXPAND|wx.ALL, border=2)
        interval_sizer.Add(interval_unit_button, flag=wx.EXPAND|wx.ALL, border=2)
        interval_sizer.AddSpacer(8)
        bottom_box.Add(interval_sizer, flag=wx.EXPAND|wx.ALL, border=5)

        self.interval = self.interval_spinbox.GetValue()
        self.interval_units = interval_unit_button.GetLabel()

        #download button
        download_button = wx.Button(self, label="Download Data")
        download_button.Bind(wx.EVT_BUTTON, self.on_download_click)
        bottom_box.Add(download_button, flag=wx.EXPAND|wx.ALL, border=2)

        #process images button
        processor_sizer = wx.BoxSizer(wx.HORIZONTAL)
        process_button = wx.Button(self, label="Process Data")
        resolution_button = wx.Button(self, label="low_res")
        self.resolution = resolution_button.GetLabel()
        blend_images_toggle = wx.CheckBox(self, label="Apply blending?")
        blend_images_toggle.SetValue(True)

        process_button.Bind(wx.EVT_BUTTON, self.on_process_click)
        resolution_button.Bind(wx.EVT_BUTTON, self.on_resolution_click)
        blend_images_toggle.Bind(wx.EVT_CHECKBOX, self.on_blend_images_toggle)

        bottom_box.Add(process_button, flag=wx.EXPAND|wx.ALL, border=2)
        processor_sizer.Add(resolution_button, flag=wx.EXPAND|wx.ALL, border=2)
        processor_sizer.Add(blend_images_toggle, flag=wx.EXPAND|wx.ALL, border=2)
        bottom_box.Add(processor_sizer, flag=wx.EXPAND|wx.ALL, border=2)

        #add the top and bottom boxes to the sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(top_box, flag=wx.EXPAND)
        sizer.Add(bottom_box, flag=wx.EXPAND)
        self.SetSizer(sizer)
    
    def get_satellite_names(self, satellites) -> list:
        #converts the button names to names that play nice with the program
        names = []

        for satellite in satellites:
            match satellite:
                case "GOES-16":
                    names.append('goes_east')
                case "GOES-18":
                    names.append('goes_west')
                case "Himawari-9":
                    names.append('himawari')
                case "Meteosat-9":
                    names.append('meteosat_9')
                case "Meteosat-10":
                    names.append('meteosat_10')

        return names

    def on_satellite_toggle(self, event, satellite):
        #get the name of the satellite
        name = self.get_satellite_names([satellite])[0]

        #if the satellite is checked, add it to the list of selected satellites
        if event.IsChecked():
            self.selected_satellites.append(satellite) #add the satellite to the list of selected satellites
            self.satellite_combo.Append(satellite) #add the satellite to the satellite combo box for composite selection
            wx.PostEvent(self, SatelliteToggleEvent(self.myEVT_SATELLITE_TOGGLE, name, True))
            #set the folder button to be enabled
            self.file_select_buttons[satellite].Enable()

        elif satellite in self.selected_satellites:
            self.selected_satellites.remove(satellite) 
            self.satellite_combo.Delete(self.satellite_combo.FindString(satellite))
            self.selected_composites.pop(satellite, None)
            wx.PostEvent(self, SatelliteToggleEvent(self.myEVT_SATELLITE_TOGGLE, name, False))
            #set the folder button to be disabled
            self.file_select_buttons[satellite].Disable()

        self.update_composites()

    def on_folder_select(self, event, satellite):
        name = self.get_satellite_names([satellite])[0]

        #open a file dialog to select the images
        wildcard = "PNG files (*.png)|*.png"
        dlg = wx.FileDialog(self, "Select PNG images", style=wx.FD_OPEN | wx.FD_MULTIPLE, wildcard=wildcard)
        selected_files = []

        if dlg.ShowModal() == wx.ID_OK:
            selected_files = dlg.GetPaths()
        
        dlg.Destroy()

        #post an event to the OpenGL canvas
        if (selected_files):
            wx.PostEvent(self, ImageSelectionEvent(self.myEVT_IMAGE_SELECTION, name, selected_files))

            #update the slider so that it has the correct number of images
            num_files = len(selected_files)
            self.slider.SetMax(num_files - 1)
            self.slider.SetValue(0)

    def on_slider_change(self, event):
        value = event.GetInt()
        self.slider_value = value
        #post an event to the OpenGL canvas
        wx.PostEvent(self, SliderChangeEvent(self.myEVT_SLIDER_CHANGE, value))

    def on_timelapse_click(self, event):
        names = self.get_satellite_names(self.selected_satellites)
        resolution = self.resolution
        dlg = wx.DirDialog(self, "Select or Create a Project Folder", style=wx.DD_DEFAULT_STYLE)

        selected_folder = None
        if dlg.ShowModal() == wx.ID_OK:
            selected_folder = dlg.GetPath()
        
        dlg.Destroy()

        #create the timelapses subdirectory
        if (selected_folder is not None):
            os.makedirs(selected_folder + '/images/timelapses', exist_ok=True)
            #post an event to the OpenGL canvas
            wx.PostEvent(self, TimelapseClickEvent(self.myEVT_TIMELAPSE_CLICK, names, selected_folder, resolution))

    def on_satellite_combo_change(self, event):
        self.update_composites()

    def update_composites(self):
        #we want to update the displayed composites but preserve the user's selections
        self.displayed_composites.Clear()
        selected_satellite = self.satellite_combo.GetValue()
        composites = self.satellite_composites.get(selected_satellite, []) #available composites for the satellite

        #add the composites to the list of displayed composites
        for composite in composites:
            self.displayed_composites.Append(composite)
            
            if (composite in self.selected_composites.get(selected_satellite, [])):
                self.displayed_composites.Check(self.displayed_composites.FindString(composite), True)

    def on_composite_checkbox_change(self, event):
        selected_satellite = self.satellite_combo.GetValue()
        selected_composites = [self.displayed_composites.GetString(i) for i in self.displayed_composites.GetCheckedItems()]
        self.selected_composites[selected_satellite] = selected_composites

    def on_interval_change(self, event):
        self.interval = self.interval_spinbox.GetValue()

    def on_interval_unit_click(self, event):
        interval_units = ["Minutes", "Hours", "Days"]
        self.interval_unit_idx = (self.interval_unit_idx + 1) % len(interval_units)
        interval_unit = interval_units[self.interval_unit_idx]
        event.GetEventObject().SetLabel(interval_unit)

    def _create_subdirectories(self, project_folder, satellites):
        subdirectories = ["data", "images"]  # List of subdirectories to create
        for subdir in subdirectories:
            subdir_path = os.path.join(project_folder, subdir)
            satellite_filepaths = [subdir_path + f'/{satellite}' for satellite in satellites]
                
            for filepath in satellite_filepaths:
                if (not os.path.exists(filepath)):
                    os.makedirs(filepath, exist_ok=True)

    def on_download_click(self, event):
        names = []
        composites = {}

        #initialize the start_time, end_time, and interval variables
        wx_start_date = self.start_datetime_edit.GetValue()
        wx_start_time = self.start_time_edit.GetValue()
        self.start_time = datetime(year=wx_start_date.GetYear(), month=wx_start_date.GetMonth() + 1, day=wx_start_date.GetDay(),
                                   hour=wx_start_time.GetHour(), minute=wx_start_time.GetMinute(), second=wx_start_time.GetSecond(), tzinfo=timezone.utc)

        wx_end_date = self.end_datetime_edit.GetValue()
        wx_end_time = self.end_time_edit.GetValue()
        self.end_time = datetime(year=wx_end_date.GetYear(), month=wx_end_date.GetMonth() + 1, day=wx_end_date.GetDay(),
                                 hour=wx_end_time.GetHour(), minute=wx_end_time.GetMinute(), second=wx_end_time.GetSecond(), tzinfo=timezone.utc)

        if (self.interval_unit_idx == 0): #minutes
            self.interval = self.interval_spinbox.GetValue()
        elif (self.interval_unit_idx == 1): #hours
            self.interval = self.interval_spinbox.GetValue() * 60
        elif (self.interval_unit_idx == 2): #days
            self.interval = self.interval_spinbox.GetValue() * 60 * 24

        names = self.get_satellite_names(self.selected_satellites)
        composites = [self.selected_composites[satellite] for satellite in self.selected_satellites]
        #convert composite keys to 'names'
        composites = dict(zip(names, composites))
        
        dlg = wx.DirDialog(self, "Select or Create a Project Folder", style=wx.DD_DEFAULT_STYLE)

        if dlg.ShowModal() == wx.ID_OK:
            selected_folder = dlg.GetPath()

        self._create_subdirectories(selected_folder, names)

        if (self.interval and self.start_time and self.end_time and self.selected_composites):
            download_manager = DownloadManager(names)
            channels = []

            for satellite in self.selected_satellites:
                helper = self.composite_helpers[satellite]
                sat_channels = []

                for composite in self.selected_composites[satellite]:
                    sat_channels.extend(helper.get_composite_channels(composite))

                sat_channels = list(dict.fromkeys(sat_channels))
                channels.append(sat_channels)
            
            download_manager.specify_start_end(self.start_time, self.end_time, self.interval)
            download_manager.specify_channels(channels)
            
            try:
                download_thread = DownloadWorker(self, download_manager, selected_folder + '/')
                download_thread.start()
            except Exception as e:
                print(e)

        else:
            print("Error: Please specify a start time, end time, interval, and at least one composite.")

    def on_process_click(self, event):
        names = self.get_satellite_names(self.selected_satellites)
        composites = [self.selected_composites[satellite] for satellite in self.selected_satellites]
        #convert composite keys to 'names'
        composites = dict(zip(names, composites))

        #ask for a folder to process
        dlg = wx.DirDialog(self, "Select a Project Folder", style=wx.DD_DEFAULT_STYLE)
        selected_folder = None

        if dlg.ShowModal() == wx.ID_OK:
            selected_folder = dlg.GetPath()
        
        if (selected_folder is not None):
            image_processor = ImageProcessor(selected_folder + '/')
            image_processor.add_satellites(composites)
            image_processor.specify_image_params(self.resolution, self.blend_images)
            
            try:
                process_worker_thread = ProcessorWorker(image_processor)
                process_worker_thread.start()
            except Exception as e:
                print(e)

    def on_resolution_click(self, event):
        #change the label
        if (self.resolution == "low_res"):
            event.GetEventObject().SetLabel("medium_res")
        elif (self.resolution == "medium_res"):
            event.GetEventObject().SetLabel("high_res")
        elif (self.resolution == "high_res"):
            event.GetEventObject().SetLabel("low_res")

        self.resolution = event.GetEventObject().GetLabel()
    
    def on_blend_images_toggle(self, event):
        self.blend_images = event.IsChecked()