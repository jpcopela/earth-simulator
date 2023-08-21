import boto3
from botocore import UNSIGNED
from botocore.config import Config
import eumdac
import requests
import shutil
from glob import glob
from math import floor
from datetime import datetime, timedelta, timezone
import numpy as np
from pathlib import Path
from tqdm import tqdm
import bz2
from concurrent.futures import ThreadPoolExecutor
import os

#eumetsat credentials
key = 'your_key'
secret = 'your_secret'

#DownloadManager class has attributes for the satellites to be downloaded, the start and end times,
#and the interval between downloads. These are initialized by the user using the GUI.
class DownloadManager():
    def __init__(self, satellites : list) -> None:
        self.satellites = satellites
        self._initialize_prerequisites()

    def _initialize_prerequisites(self) -> None:
        buckets = []
        aws_prefixes = []
        
        #get bucket and prefix for each satellite
        for satellite in self.satellites:
            match satellite:
                case 'goes_east':
                    bucket = 'noaa-goes16'
                    aws_prefix = 'ABI-L1b-RadF'
                case 'goes_west':
                    bucket = 'noaa-goes17'
                    aws_prefix = 'ABI-L1b-RadF'
                case 'himawari':
                    bucket = 'noaa-himawari8'
                    aws_prefix = 'AHI-L1b-FLDK'
                case 'meteosat_9':
                    bucket = None
                    aws_prefix = None
                case 'meteosat_10':
                    bucket = None
                    aws_prefix = None
                case _:
                    raise ValueError('Invalid satellite option.')
                
            buckets.append(bucket)
            aws_prefixes.append(aws_prefix)
        
        if (any(['himawari' or 'goes' in i for i in self.satellites])):
            self.client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
        
        if (any(['meteosat' in i for i in self.satellites])):
            credentials = (key, secret)

            try:
                eumetsat_token = eumdac.AccessToken(credentials)
            except requests.exceptions.HTTPError as error:
                print(f"Error when tryng the request to the server: '{error}'")

            self.token = eumetsat_token
        
        self.buckets = buckets
        self.aws_prefixes = aws_prefixes
        

    def generate_channels(self, composites : dict):
        #generate the required channels for the satellite based on the 
        #desired image types (composites)
        required_channels = []

        for satellite in composites:
            if ('himawari' in satellite):
                temp_channels = []
                
                for composite in composites[satellite]:
                    if ('natural_color' in composite):
                        temp_channels.extend(['B02', 'B03', 'B04', 'B05'])
                    elif ('true_color' in composite):
                        temp_channels.extend(['B01', 'B02', 'B03', 'B04'])
                    elif ('night_ir_alpha' in composite):
                        temp_channels.extend(['B07', 'B13', 'B15'])
                    else:
                        #else, we are getting passed an individual channel
                        temp_channels.extend(composite)

                required_channels.append(temp_channels)

            elif ('goes' in satellite):
                temp_channels = []

                for composite in composites[satellite]:
                    if ('natural_color' in composite):
                        temp_channels.extend(['C05', 'C02', 'C03'])
                    elif ('true_color' in composite):
                        temp_channels.extend(['C01', 'C02', 'C03'])
                    elif ('night_ir_alpha' in composite):
                        temp_channels.extend(['C07', 'C13', 'C15'])
                    else:
                        #else, we are getting passed an individual channel
                        temp_channels.extend(composite)

                required_channels.append(temp_channels)

            elif ('meteosat' in composites[satellite]):
                return None
            
            else:
                raise ValueError('Invalid satellite option. Use "himawari", "goes_east", "goes_west", meteosat_10, or meteosat_9 instead.')
            
            self.channels = required_channels

    def specify_channels(self, channels : list) -> None:
        self.channels = channels

    def specify_start_end(self, start : datetime, end : datetime, interval_minutes : int) -> None:
        #data are generally stored in 10 minute intervals
        times = [(start + timedelta(minutes=i)) for i in range(0, round((end - start).total_seconds()) // 60, round(interval_minutes))]
        self.floored_times = [i - timedelta(minutes=i.minute % 10, seconds=i.second, microseconds=i.microsecond) for i in times]
        self.start, self.end, self.interval = start, end, interval_minutes

    #the user calls the download_data() function to download their requested satellite data from start
    #to end at the specified interval
    def download_data(self, project_folder : str) -> None:
        self.project_folder = project_folder

        if (self.satellites and self.channels and self.start and self.end and self.interval):
            for i in range(len(self.satellites)):
                if ('goes' in self.satellites[i] or 'himawari' in self.satellites[i]):
                    self._download_aws_data(self.satellites[i], self.channels[i])
                elif 'meteosat' in self.satellites[i]:
                    timestamps = self._get_meteosat_timestamps(self.satellites[i])
                    self._download_meteosat_data(self.satellites[i], timestamps)
        else:
            print("Satellite, time, and channel information must be submitted before downloading.")
        
    def _get_meteosat_timestamps(self, satellite):
        #meteosat data uses the eumetsat API, so we can just find the files for our time interval
        token = self.token
        datastore = eumdac.DataStore(token)

        if (satellite == 'meteosat_10'):
            #0 degree longitude satellite
            collection_id = 'EO:EUM:DAT:MSG:HRSEVIRI'
        elif (satellite == 'meteosat_9'):
            #45 degree longitude "indian ocean" satellite
            collection_id = 'EO:EUM:DAT:MSG:HRSEVIRI-IODC'
        else:
            raise ValueError(f'Invalid satellite option: {satellite}.')

        try:    
            selected_collection = datastore.get_collection(collection_id)
        except eumdac.datastore.DataStoreError as error:
            print(f"Error related to the data store: '{error.msg}'")
        except eumdac.collection.CollectionError as error:
            print(f"Error related to the collection: '{error.msg}'")
        except requests.exceptions.RequestException as error:
            print(f"Unexpected error: {error}")

        products = []
        #to account for the possibility of someone wanting to download over a long time period,
        #products will be aquired in a for loop over the time interval
        for i in range(len(self.floored_times) - 1):
            start = self.floored_times[i] - timedelta(minutes=5)
            end = self.floored_times[i] + timedelta(minutes=5)

            #get the products for the time interval and select the first one
            #for some reason this wasn't working as it's supposed to until I added the native_name call
            product = selected_collection.search(dtstart=start, dtend=end).first()

            products.append(product)

        #remove duplicates
        products = list(dict.fromkeys(products))

        return products

    def _download_aws_data(self, satellite, channels):
        data_file_path = self.project_folder + f'data/{satellite}/'
        existing_data_files = glob(data_file_path + '*')
        bucket = self.buckets[self.satellites.index(satellite)]

        files = self._get_channel_files(satellite, channels)        
        filenames = [i.split('/')[-1] for i in files]
        local_ch_filenames = [data_file_path + i for i in filenames] #must account for bz2 decompression changing file name

        remove_files = []

        with tqdm(total=len(files)) as pbar:
            #if channel filenames are not in the existing data files already, download them
            for i in range(len(files)):
                filename = files[i].split('/')[-1]

                if (not (np.any([local_ch_filenames[i] in j for j in existing_data_files]) or np.any([local_ch_filenames[i][:-4] in j for j in existing_data_files]))):
                    try:
                        self.client.download_file(bucket, files[i], local_ch_filenames[i])
                    except:
                        print(f'Failed to download {files[i]}')
                        #remove_files.append(local_ch_filenames[i])
                
                else:
                    print(f'{filename} already exists.')

                pbar.update(1)
                tqdm.set_description(pbar, f'{filename}')

        if (satellite == 'himawari'):
            self._unzip_himawari_data(glob(self.project_folder + 'data/himawari/*.bz2'))
            remove_files.extend(glob(self.project_folder + 'data/himawari/*.bz2')) #add the bz2 files to the list of files to be removed

        self._remove_files(remove_files)

    def _download_meteosat_data(self, satellite, timestamps):
        data_file_path = self.project_folder + f'data/{satellite}/'
        existing_data_files = glob(data_file_path + '*')

        native_name = [f'{product}.nat' for product in timestamps]

        with tqdm(total=len(timestamps), desc=f'Downloading {satellite} data...') as pbar:
            for i in range(len(timestamps)):
                if (not np.any([native_name[i] in j for j in existing_data_files])):
                    try:
                        with timestamps[i].open(entry=native_name[i]) as fsrc, \
                            open(f'{data_file_path}/{fsrc.name}', mode='wb') as fdst:
                            shutil.copyfileobj(fsrc, fdst)
                    except eumdac.product.ProductError as error:
                        print(f"Error related to the product '{timestamps[i]}' while trying to download it: '{error.msg}'")
                    except requests.exceptions.RequestException as error:
                        print(f"Unexpected error: {error}")
                else:
                    print (f'File {native_name[i]} already exists.')

                pbar.update(1)

    def _get_channel_files(self, satellite, channels):
        channel_files = []
        bucket = self.buckets[self.satellites.index(satellite)]
        aws_prefix = self.aws_prefixes[self.satellites.index(satellite)]

        with tqdm(total=len(self.floored_times), desc=f'Gathering {satellite} files.') as pbar:
            for time in self.floored_times:
                if ('goes' in satellite):
                    #goes data beginning at <Hour>:00 is stored in the previous hour's folder
                    if (time.strftime('%M') == '00'):
                        corrected_time = time - timedelta(minutes=5) #subtract 5 minutes so we are in the previous hour now
                        timestamp = corrected_time.strftime(f'{aws_prefix}/%Y/%j/%H/')
                    else:
                        timestamp = time.strftime(f'{aws_prefix}/%Y/%j/%H/')

                elif ('himawari' in satellite):
                    timestamp = time.strftime(f'{aws_prefix}/%Y/%m/%d/%H%M/')

                for channel in channels:
                    response = self.client.list_objects_v2(Bucket=bucket, Prefix=timestamp)

                    for content in response.get('Contents', []):
                        if ('himawari' in satellite):
                            if (channel in content['Key'] and time.strftime('%H%M') in content['Key']):
                                channel_files.append(content['Key'])
                        
                        elif ('goes' in satellite):
                            if (channel in content['Key'] and (time >= content['LastModified'] - timedelta(minutes=2) and time <= content['LastModified'] + timedelta(minutes=2))):
                                channel_files.append(content['Key'])
                
                pbar.update()

        return channel_files

    def _decompress_file(file, pbar=None):
        with bz2.open(file, 'rb') as f_in:
            content = f_in.read()

            with open(file[:-4], 'wb') as f_out:
                f_out.write(content)
                pbar.update(os.path.getsize(file))
        
    def _unzip_himawari_data(self, files):
        with ThreadPoolExecutor() as executor:
            total_size = sum(os.path.getsize(input_filename) for input_filename in files)
            with tqdm(total=total_size, unit='B', unit_scale=True, desc='Decompressing Himawari files...') as pbar:
                futures = [executor.submit(DownloadManager._decompress_file, input_filename, pbar)
                            for input_filename in files]
                for future in futures:
                    future.result()

    def _remove_files(self, files):
        for file in files:
            Path(file).unlink()

