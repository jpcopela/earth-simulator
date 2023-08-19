import os
from glob import glob

from src.download_manager import DownloadManager
from src.data_processor import ImageProcessor
from src.image_handler import ImageBlender

from datetime import datetime
import numpy as np

#check the data files in images/alpha_masks, images/blending_masks
#check the data in data/texture_coords, data/vertex_coords

neighboring_satellites = {
    'goes_east' : ['goes_west', 'meteosat_10'],
    'goes_west' : ['goes_east', 'himawari'],
    'himawari' : ['goes_west', 'meteosat_9'],
    'meteosat_9' : ['himawari', 'meteosat_10'],
    'meteosat_10' : ['meteosat_9', 'goes_east']
}

class AppDiagnostics():
    def __init__(self, attempt_fix=False, resolutions: list=[]):
        self.satellites = ['goes_east', 'goes_west', 'himawari', 'meteosat_9', 'meteosat_10']
        self.channels = {'goes_east' : ['C01'], 'goes_west' : ['C01'], 'himawari' : ['B01'], 
                         'meteosat_9' : ['VIS006'], 'meteosat_10' : ['VIS006']}
        self.resolutions = resolutions
        self.missing_resolutions = []
        self.missing_alpha_mask_files = None
        self.missing_blending_mask_files = None
        
    def run_diagnotics(self):
        self._check_alpha_masks()
        self._check_blending_masks()
        self.missing_resolutions = list(dict.fromkeys(self.missing_resolutions))

    def query_user(self, resolution):
        print(f'Would you like to attempt to generate {resolution} blending files? (Y/N)')

    def attempt_fix(self, resolution: str):
        if self.missing_alpha_mask_files is not None and self.missing_blending_mask_files is not None:
            self._attempt_fix_alpha_masks(resolution)
            self._attempt_fix_blending_masks(resolution)
        else:
            print('Please run diagnostics before attempting to generate files.')

    def _check_alpha_masks(self):
        path = 'images/alpha_masks/'
        self.missing_alpha_mask_files = []

        for res in self.resolutions:
            files = os.listdir(path + res + '/')

            for name in self.satellites:
                if (not np.any([name in i for i in files])):
                    self.missing_alpha_mask_files.append((res, name))

            if (np.any([res in i for i in self.missing_alpha_mask_files])):
                self.missing_resolutions.append(res)
                print(f'Missing {res} alpha masks.')

    #to create the blending masks we need to generate a tiff file for each satellite
    def _check_blending_masks(self):
        path = 'images/blending_masks/'
        self.missing_blending_mask_files = []

        for res in self.resolutions:
            files = os.listdir(path + res + '/')

            for satellite in neighboring_satellites:
                for neighbor in neighboring_satellites[satellite]:
                    mask_name = f'{satellite}_{neighbor}.npy'

                    if (np.any([mask_name in i for i in files])):
                        continue

                    else:
                        self.missing_resolutions.append(res)
                        self.missing_blending_mask_files.append((res, satellite, neighbor))

            if (np.any([res in i for i in self.missing_blending_mask_files])):
                print(f'Missing {res} blending masks.')

    def _attempt_fix_alpha_masks(self, resolution):
        if len(self.missing_alpha_mask_files) > 0:
            for res, name in self.missing_alpha_mask_files:
                if res in resolution:
                    print(f'Attempting to generate {res} alpha masks for {name}.')
                    
                    #generate the directory
                    os.makedirs(f'data/{name}/', exist_ok=True)

                    #download a small amount of image data
                    download_manager = DownloadManager([name])
                    print(self.channels[name])
                    download_manager.specify_channels([self.channels[name]])
                    download_manager.specify_start_end(datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 0, 10), 1)

                    image_processor = ImageProcessor('')
                    composite = {name : self.channels[name]}
                    image_processor.add_satellites(composite)
                    image_processor.specify_image_params(res)

                    try:
                        download_manager.download_data('')
                    except Exception as e:
                        print(f'Failed to download data.')
                        print(e)                            
                    
                    try:
                        image_processor.create_alpha_masks(name)
                    except Exception as e:
                        print(f'Failed to create alpha masks.')
                        print(e)

    def _attempt_fix_blending_masks(self, resolution):
        if len(self.missing_blending_mask_files) > 0:
            for res, satellite, neighbor in self.missing_blending_mask_files:
                if res in resolution:
                    mask_name = f'{satellite}_{neighbor}.npy'

                    print(f'Attempting to generate {res} {mask_name}.')

                    #generate the directory
                    os.makedirs(f'data/{satellite}/', exist_ok=True)

                    #download a small amount of image data
                    download_manager = DownloadManager([satellite, neighbor])
                    download_manager.specify_channels([self.channels[neighbor], self.channels[neighbor]])
                    download_manager.specify_start_end(datetime(2023, 1, 1, 0, 0), datetime(2023, 1, 1, 0, 10), 1)

                    image_processor = ImageProcessor('')
                    composites = {satellite : self.channels[satellite], neighbor : self.channels[neighbor]}
                    image_processor.add_satellites(composites)
                    image_processor.specify_image_params(res)

                    try:
                        download_manager.download_data('')
                    except Exception as e:
                        print(f'Failed to download data.')
                        print(e)                            
                    
                    try:
                        image_processor.generate_images_from_data(satellite, 'tif')
                        image_processor.generate_images_from_data(neighbor, 'tif')
                    except Exception as e:
                        print(f'Failed to create blending mask.')
                        print(e)
                    
                    ImageBlender(satellite, neighbor, res)


if __name__ == '__main__':
    app_diagnostics = AppDiagnostics(attempt_fix=True, resolutions=['low_res', 'medium_res', 'high_res'])
    app_diagnostics.run_diagnotics()
    app_diagnostics.attempt_fix(['low_res', 'medium_res'])
