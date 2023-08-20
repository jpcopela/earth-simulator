import wx

from src.widgets.main_widget import MainWindow

class EarthSimulatorApp(wx.App):
    def OnInit(self):
        frame = MainWindow(None, title="Earth Simulator")
        frame.Show()
        return True

if __name__ == "__main__":
    app = EarthSimulatorApp(False)
    app.MainLoop()
