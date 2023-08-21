# earth-simulator
Application for downloading,  processing, and viewing geostationary remote sensing data in three dimensions

# Dependencies
It is recommended to create a virtual environment in the project folder. Dependencies can be installed using pip:  
`pip install -r requirements.txt`  

wxPython must be installed for your specific platform. On linux, see https://wiki.wxpython.org/How%20to%20install%20wxPython#Installing_wxPython-Phoenix_using_pip for info for your specific distro.  

For Windows and MacOS, run:  
`pip install -U wxPython`  

You should also replace the satpy areas.yaml file with the one provided in the repo in order for low-resolution images to work, e.g.  
`cp areas.yaml lib/python3.10/site-packages/satpy/etc/areas.yaml`

# Additional info
Currently you must manually change satellite names for GOES West and Himawari-9 if you want images older than their current stage. For example, to get GOES-17 images, change 'noaa-goes18' to 'noaa-goes17' in the download manager. For Himawari, change 'noaa-himawari9' to 'noaa-himawari8'.

On Ubuntu you must run the following command before running the script:
`export PYOPENGL_PLATFORM='egl'`
