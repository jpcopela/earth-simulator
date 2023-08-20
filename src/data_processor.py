import dask
from satpy import Scene
from satpy import find_files_and_readers
from satpy.modifiers import angles
from satpy.resample import get_area_def
from pyresample import create_area_def
from glob import glob
from PIL import Image
import numpy as np
from pathlib import Path
from PIL import Image

from datetime import timedelta

from tqdm import tqdm

class ImageProcessor():
    def __init__(self, project_folder) -> None:
        self.project_folder = project_folder
        self.filenames = {}

    def add_satellites(self, composites : dict) -> None:
        self.satellites = [i for i in composites.keys()]
        self.composites = composites

    def specify_image_params(self, resolution : str, apply_blending=False) -> None:
        self.resolution = resolution
        self.apply_blending = apply_blending

    def process_images(self):
        for satellite in self.satellites:
            self.generate_images_from_data(satellite, 'png')

        self._apply_alpha_masks() #apply the alpha masks to the images

        if (self.apply_blending):
            self._blend_images()

        print('Done!')
    
    def _get_satpy_kwargs(self, satellite : str) -> dict:
        if (satellite == 'himawari'):
            mode = 'native'
            reader = 'ahi_hsd'
            
            match self.resolution:            
                case 'low_res': 
                    resample_area = create_area_def("himawari_area_def", area_extent=(-5500000.0355, -5500000.0355, 5500000.0355, 5500000.0355), projection='+proj=geos +h=35785831.0 +lon_0=140.7 +sweep=y', height=2750, width=2750)
                case 'medium_res':
                    resample_area = create_area_def("himawari_area_def", area_extent=(-5500000.0355, -5500000.0355, 5500000.0355, 5500000.0355), projection='+proj=geos +h=35785831.0 +lon_0=140.7 +sweep=y', height=5500, width=5500)
                case 'high_res':
                    resample_area = create_area_def("himawari_area_def", area_extent=(-5500000.0355, -5500000.0355, 5500000.0355, 5500000.0355), projection='+proj=geos +h=35785831.0 +lon_0=140.7 +sweep=y', height=11000, width=11000)

        elif (satellite == 'goes_east'):
            reader = 'abi_l1b'
            mode = 'native'

            match self.resolution:
                case 'low_res':
                    resample_area = get_area_def('goes_east_abi_f_4km')
                case 'medium_res':
                    resample_area = get_area_def('goes_east_abi_f_2km')
                case 'high_res':
                    resample_area = get_area_def('goes_east_abi_f_500m')

        elif (satellite == 'goes_west'):
            reader = 'abi_l1b'
            mode = 'native'

            match self.resolution:
                case 'low_res':
                    resample_area = get_area_def('goes_west_abi_f_4km')
                case 'medium_res':
                    resample_area = get_area_def('goes_west_abi_f_2km')
                case 'high_res':
                    resample_area = get_area_def('goes_west_abi_f_500m')

        elif (satellite == 'meteosat_10'):
            mode = 'native'
            reader = 'seviri_l1b_native'

            match self.resolution:
                case 'low_res':
                    resample_area = 'msg_seviri_fes_3km'
                case 'medium_res':
                    resample_area = 'msg_seviri_fes_3km'
                case 'high_res':
                    resample_area = 'msg_seviri_fes_1km'

        elif (satellite == 'meteosat_9'):
            mode = 'native'
            reader = 'seviri_l1b_native'

            match self.resolution:
                case 'low_res':
                    resample_area = 'msg_seviri_iodc_3km'
                case 'medium_res':
                    resample_area = 'msg_seviri_iodc_3km'
                case 'high_res':
                    resample_area = 'msg_seviri_iodc_1km'
        else:
            raise ValueError('Invalid satellite option. Use "himawari", "goes_east", "goes_west", meteosat_10, or meteosat_9 instead.')
        
        kwargs = {'mode': mode, 'reader': reader, 'resample_area': resample_area}

        return kwargs
    
    #get timestamps for images for a given satellite
    def _find_image_timestamps(self, satellite : str) -> list:
        data_filepath = self.project_folder + f'data/{satellite}/'
        files = glob(data_filepath + '*')

        print(data_filepath, files)
        
        if files:
            reader = self._get_satpy_kwargs(satellite)['reader']
            file_timestamps = []

            #get timestamp for each file
            for file in files:
                file_scn = Scene(filenames=[file], reader=reader)
                file_timestamps.append(file_scn.start_time)

            #remove duplicates
            file_timestamps = list(dict.fromkeys(file_timestamps))

            #sort
            file_timestamps.sort()
            deltas = np.diff(file_timestamps).tolist()
            deltas.append(timedelta(minutes=600)) #add a last element so we can catch the last timestamp

            #collect files for each timestamp
            time_ordered_files = [find_files_and_readers(base_dir=data_filepath, reader=reader,
                                                        start_time=file_timestamps[i], end_time=file_timestamps[i] + (deltas[i] / 2.0))[reader] for i in range(len(file_timestamps))]
            
            file_scn.unload()

            return time_ordered_files

    def _get_dask_configs(self):
        match self.resolution:
            case 'low_res':
                dask.config.set(num_workers=6)
                self.chunk_size = {'array.chunk-size' : '12MiB'}
            case 'medium_res':
                dask.config.set(num_workers=6)
                self.chunk_size = {'array.chunk-size' : '24MiB'}
            case 'high_res':
                dask.config.set(num_workers=6)
                self.chunk_size = {'array.chunk-size' : '24MiB'}
       
    def generate_images_from_data(self, satellite, extension : str) -> None:
        self._get_dask_configs()

        with dask.config.set(self.chunk_size):
            self.filenames[satellite] = []

            output_file_name = self.project_folder + f'images/{satellite}/{self.resolution}/{satellite}'

            kwargs = self._get_satpy_kwargs(satellite)
            composites = self.composites[satellite]

            time_ordered_files = self._find_image_timestamps(satellite)
            print(time_ordered_files)

            if (not time_ordered_files):
                print(f'No data found for {satellite}.')
                return

            with tqdm(total=len(time_ordered_files)) as pbar:
                for files in time_ordered_files:        
                    scn = Scene(filenames=files, reader=kwargs['reader'])

                    for composite in composites:
                        scn.load([composite], generate=False, upper_right_corner='NE')
                
                    if (kwargs['resample_area'] == 'none'):
                        kwargs['resample_area'] = scn.coarsest_area()
                    
                    resampled_scn = scn.resample(kwargs['resample_area'], resampler=kwargs['mode'], reduce_data=False)

                    for composite in composites:
                        timestamp = resampled_scn[composite].attrs['start_time'].strftime('%Y%m%d_%H%M')
                        
                        if (not glob(output_file_name + f'_{composite}_{timestamp}.png')):
                            tqdm.set_description(pbar, f'Processing {satellite} at {timestamp}.')

                            try:
                                resampled_scn.save_dataset(dataset_id=composite, filename=output_file_name + f'_{composite}_{timestamp}.' + extension)
                                self.filenames[satellite].append(output_file_name + f'_{composite}_{timestamp}.' + extension)
                            except:
                                print(f'failed to download {output_file_name}_{composite}_{timestamp}.{extension}')
                                pass
                        else:
                            print(f'{output_file_name}_{composite}_{timestamp}.{extension} already exists')

                    pbar.update(1)

    #this method generates only the scene
    def _generate_scene_from_data(self, satellite : str) -> None:
        with dask.config.set({"array.chunk-size" : "12MiB"}):
            kwargs = self._get_satpy_kwargs(satellite)
            composites = self.composites[satellite]

            time_ordered_files = self._find_image_timestamps(satellite)

            for files in time_ordered_files:
                scn = Scene(filenames=files, reader=kwargs['reader'])

                for composite in composites:
                    scn.load([composite], generate=False, upper_right_corner='NE')
                
                if (kwargs['resample_area'] == 'none'):
                    kwargs['resample_area'] = scn.coarsest_area()
                
                self.scn = scn.resample(kwargs['resample_area'], resampler=kwargs['mode'], reduce_data=False)

    def _apply_alpha_masks(self):
        total_iterations = [files for satellite in self.filenames for files in self.filenames[satellite]]
        with tqdm(total=len(total_iterations)) as pbar:
            #for each generated composite, apply the blending mask
            for satellite in self.filenames:
                alpha_vals = np.load(f'images/alpha_masks/{self.resolution}/{satellite}_alpha_mask.npy')
                
                for file in self.filenames[satellite]:
                    tqdm.set_description(pbar, f'Applying alpha mask to {file.split("/")[-1]}.')
                    img_arr = np.asarray(Image.open(file)).copy()

                    alpha = np.where(img_arr[:, :, 3] != 0, alpha_vals, 0)
                    img_arr[:, :, 3] = alpha
                    
                    image = Image.fromarray(img_arr)
                    image.save(file)

                    pbar.update(1)

    def _get_neighboring_satellites(self, satellite : str) -> list:
        #return a list of the neighboring satellites to the given satellite
        #ordered [east, west]
        match satellite:
            case 'himawari':
                return ['goes_west', 'meteosat_9']
            case 'goes_east':
                return ['meteosat_10', 'goes_west']
            case 'goes_west':
                return ['goes_east', 'himawari']
            case 'meteosat_10':
                return ['meteosat_9', 'goes_east']

    def _get_image_pairs(self, satellite : str) -> list:
        #get the image pairs based on the neighboring satellites
        #and the available images in the project folder
        neighboring_satellites = self._get_neighboring_satellites(satellite)
        my_files = glob(self.project_folder + f'images/{satellite}/{self.resolution}/{satellite}*.png')
        image_pairs = []

        for file in my_files:
            str_timestamp = file.split('/')[-1].split('_')[-2] + '_' + file.split('/')[-1].split('_')[-1].split('.')[0] #we don't care about the .png extension
            neighbor_files = []

            for neighbor in neighboring_satellites:
                neighbor_file = glob(self.project_folder + f'images/{neighbor}/{self.resolution}/{neighbor}_*_{str_timestamp}.png')

                if (neighbor_file):
                    neighbor_files.append(neighbor_file[0])

            neighbor_files.append(file)
            image_pairs.append(neighbor_files)

        return image_pairs

    def _blend_images(self):
        for satellite in self.satellites:
            neighboring_satellites = self._get_neighboring_satellites(satellite)
            sat_image_pairs = self._get_image_pairs(satellite)

            with tqdm(total=len(sat_image_pairs)) as pbar:
                for pair in sat_image_pairs:
                    for neighbor in neighboring_satellites:
                        #if the neighbor is in the pair, we can blend the images
                        if (len([i for i in pair if neighbor in i]) > 0):
                            tqdm.set_description(pbar, f'Blending {satellite} and {neighbor} images...')
                            my_image = pair[-1] #each satellite is the last element in the pair

                            neighbor_image = [i for i in pair if neighbor in i][0]

                            blending_mask = np.load(f'images/blending_masks/{self.resolution}/{satellite}_{neighbor}.npy')
                            mask = np.all(blending_mask[:, :, :] != 0, axis=2)

                            weights = blending_mask[:, :, 0]
                            target_x = blending_mask[:, :, 1].astype(np.int32)
                            target_y = blending_mask[:, :, 2].astype(np.int32)

                            # Compute the inverse blending weights
                            inv_weights = 1.0 - weights

                            my_arr = np.asarray(Image.open(my_image))
                            n_arr = np.asarray(Image.open(neighbor_image))

                            # Separate the original image into RGB and alpha channels
                            rgb_channels = my_arr[:, :, :3]
                            alpha_channel = my_arr[:, :, 3]

                            other_rgb_channels = n_arr[:, :, :3]

                            # Initialize an array to store the blended result
                            blended_result = np.zeros_like(rgb_channels)

                            # Perform blending for each channel separately
                            for channel in range(3):
                                # Compute the blended pixel values
                                blended_values = (weights * rgb_channels[:, :, channel] +
                                                inv_weights * other_rgb_channels[target_x, target_y, channel])

                                # Store the blended values in the result array
                                blended_result[:, :, channel] = blended_values

                            # Combine the blended RGB channels with the original alpha channel
                            blended_image = np.dstack((blended_result, alpha_channel))

                            copy = my_arr.copy()
                            copy[mask] = blended_image[mask]
                            out_image = Image.fromarray(copy)

                            out_image.save(my_image) #this is sub-optimal, but these images are better than the originals anyway
                        
                    pbar.update(1)

    def create_alpha_masks(self, satellite : str):
        #it is good practice to send only individual channels to this function because Himawari breaks
        #for composites, but works for single channels. It is also much faster to do it this way
        self._generate_scene_from_data(satellite)
        zenith_angles = angles.get_satellite_zenith_angle(self.scn[self.composites[satellite][0]])
        angle = zenith_angles.to_numpy().astype(dtype=np.float32)
        shape = angle.shape
        alpha_vals = np.empty(shape).astype(dtype=np.float32)
        lim = 70.
        max_angle = 85.

        #get the values that are greater than lim and less than max_angle
        combined_mask = np.logical_and(angle > lim, angle < max_angle)
        greater_than = angle > max_angle
        less_than = angle < lim

        print(np.shape(combined_mask), np.shape(alpha_vals))

        alpha_vals[combined_mask] = 255 * (1. - ((angle[combined_mask] - lim) / (max_angle - lim)))
        alpha_vals[greater_than] = 0
        alpha_vals[less_than] = 255


        #todo: vectorize this code to improve speed
        #code to generate an "alpha image". Angle values are normalized to between a limit value
        #and a maximum angle value. The fine tuning of these parameters allows one to create an
        #alpha gradient near the edge of the image.
        '''for i in range(0, shape[0]):
            for j in range(0, shape[1]):
                if (angle[i, j] > lim and angle[i, j] < max_angle):
                    alpha_vals[i, j] = 255 * (1. - ((angle[i, j] - lim) / (max_angle - lim)))
                elif(angle[i, j] > max_angle):
                    alpha_vals[i, j] = 0
                else:
                    alpha_vals[i, j] = 255'''
        
        np.save(f'images/alpha_masks/{self.resolution}/{satellite}_alpha_mask.npy', alpha_vals)

    def _remove_files(files):
        for file in files:
            rem_file = Path(file)
            rem_file.unlink()

#generate alpha masks for each satellite for the 'medium_res' resolution
"""goes_east = Satellite('goes_east', ['C01'], 'medium_res', datetime(2023, 8, 7, 16, 0), datetime(2023, 8, 7, 17, 0), 1, 1)
goes_east.process_images()
goes_east.create_alpha_masks()

goes_west = Satellite('goes_west', ['C01'], 'medium_res', datetime(2023, 8, 7, 16, 0), datetime(2023, 8, 7, 17, 0), 1, 1)
goes_west.process_images()
goes_west.create_alpha_masks()

himawari = Satellite('himawari', ['B04'], 'medium_res', datetime(2023, 8, 7, 16, 0), datetime(2023, 8, 7, 17, 0), 1, 1)
himawari.process_images()
himawari.create_alpha_masks()"""