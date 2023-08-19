from datetime import datetime, timedelta
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
from src.data_processor import ImageProcessor

goes_east = ImageProcessor('goes_east', ['true_color'], 'medium_res', datetime(2023, 8, 7, 16, 0, 0), datetime(2023, 8, 7, 21, 0, 0), 5, 60)
goes_west = ImageProcessor('goes_west', ['true_color'], 'medium_res', datetime(2023, 8, 7, 16, 0, 0), datetime(2023, 8, 7, 21, 0, 0), 5, 60)
himawari = ImageProcessor('himawari', ['true_color'], 'medium_res', datetime(2023, 8, 7, 16, 0, 0), datetime(2023, 8, 7, 21, 0, 0), 5, 60)
#meteosat_9 = Meteosat('meteosat_9', ['natural_color'], 'medium_res', False)
#meteosat_10 = Meteosat('meteosat_10', ['natural_color'], 'medium_res', False)

satellites = [himawari]#, meteosat_9, meteosat_10]
def download(satellite):
    try:
        print(f'Downloading {satellite.satellite} data...')
        satellite.download_data()
    except:
        raise ValueError(f'Failed to download {satellite.satellite} data.')
    
def process(satellite):
    try:
        print(f'Processing {satellite.satellite} into {satellite.composites} image.')
        satellite.process_images()
    except:
        raise ValueError(f'Failed to process {satellite.composites} image.')

def parallel_activities():
    cpus = cpu_count()

    """try:
        cpus = cpu_count()
        pool = ThreadPool(cpus)
        results = pool.imap_unordered(download, satellites)

        for result in results:
            pass

    except:
        raise ValueError('Failed to create thread pool for downloads.')"""
    
    for satellite in satellites:
        satellite.process_images()

if __name__ == '__main__':    
    t1 = datetime.now()
    parallel_activities()
    t2 = datetime.now()
    delta = t2 - t1

    print('#########################################################')
    print('Finished! Elapsed time: ', (delta.total_seconds()) / 60.)