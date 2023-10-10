# Earth Simulator
Python application for downloading,  processing, and viewing geostationary remote sensing data in three dimensions

![Alt Text](https://github.com/jackcop/earth-simulator/blob/main/images/thumbnail.gif)


# Dependencies
It is recommended to create a virtual environment in the project folder. Dependencies can be installed using pip:  
`pip install -r requirements.txt`  

wxPython must be installed for your specific platform. On linux, see https://wiki.wxpython.org/How%20to%20install%20wxPython#Installing_wxPython-Phoenix_using_pip for info for your specific distro.  

For Windows and MacOS, run:  
`pip install -U wxPython`  

# Additional Info
Currently you must manually change satellite names for GOES West and Himawari-9 if you want images older than their current stage. For example, to get GOES-17 images, change 'noaa-goes18' to 'noaa-goes17' in the download manager. For Himawari, change 'noaa-himawari9' to 'noaa-himawari8'.

On Ubuntu you must run the following command before running the script:
`export PYOPENGL_PLATFORM='egl'`

To create timelapses from images generated using the timelapse button, you can use ffmpeg. To create an initial video, run:  
`cat $(find timelapse_0 -maxdepth 1 -name "*.png" | sort -V) | ffmpeg -framerate 3 -i - out.mp4`  

This will create a 3 frames per second video with all the images from the timelapse_0 folder, which can be found in the same directory your satellite images are in. To increase the framerate and blend the frames, run:  
`ffmpeg -i out.mp4 -vf framerate=fps=20 out_blended.mp4`  

For more info, see: https://askubuntu.com/questions/1183076/convert-all-the-png-files-in-a-folder-to-video



# Future Improvements
* Add support for more satellites, including polar orbiting ones
* Improve the UI so the app is easier and more intuitive to use
* Implement a method of dynamically selecting dask options depending on the user's hardware to make loading images faster
* Implement file size checking in the download manager so downloads are more robust and downstream errors don't occur if files aren't downloaded properly
* Improve code consistency, organization, and modularity
* Add more camera controls so the user can get cinematic angles
