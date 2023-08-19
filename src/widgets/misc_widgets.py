import wx

from threading import Thread

class UserInputEvent(wx.PyEvent):
    def __init__(self, text):
        wx.PyEvent.__init__(self)
        self.SetEventType(wx.NewEventType())
        self.text = text

class CapturedOutputChangeEvent(wx.PyEvent):
    def __init__(self):
        wx.PyEvent.__init__(self)
        self.SetEventType(wx.NewEventType())

class CapturedOutput:
    def __init__(self, text_ctrl):
        self.text_ctrl = text_ctrl

    def write(self, text):
        wx.CallAfter(self._update_text_ctrl, text)

    def _update_text_ctrl(self, text):
        self.text_ctrl.AppendText(text)
        self.text_ctrl.SetInsertionPointEnd() 

    def flush(self):
        pass

class ConfirmationDialog(wx.Dialog):
    def __init__(self, parent, resolution):
        super(ConfirmationDialog, self).__init__(parent, title="Select an option")

        yes_button = wx.Button(self, wx.ID_YES)
        no_button = wx.Button(self, wx.ID_NO)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=f"Do you want to generate {resolution} blending masks?"), 0, wx.ALL, 10)
        sizer.Add(yes_button, 0, wx.ALIGN_RIGHT | wx.RIGHT, 10)
        sizer.Add(no_button, 0, wx.ALIGN_RIGHT | wx.RIGHT, 10)
        self.SetSizerAndFit(sizer)

        yes_button.Bind(wx.EVT_BUTTON, self.on_yes)
        no_button.Bind(wx.EVT_BUTTON, self.on_no)

    def on_yes(self, event):
        self.EndModal(wx.ID_YES)

    def on_no(self, event):
        self.EndModal(wx.ID_NO)

class BottomBar(wx.Panel):
    myEVT_USER_INPUT = wx.NewEventType()
    EVT_USER_INPUT = wx.PyEventBinder(myEVT_USER_INPUT, 1)    

    def __init__(self, parent):
        wx.Panel.__init__(self, parent)

        self.text_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_PROCESS_ENTER)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.text_ctrl, 1, wx.EXPAND)
        self.SetSizer(sizer)

#worker class for creating blending masks
class AttemptFixWorker(Thread):
    def __init__(self, parent, resolution):
        Thread.__init__(self)
        self.parent = parent
        self.resolution = resolution

    def run(self):
        self.parent.file_status.attempt_fix(self.resolution)