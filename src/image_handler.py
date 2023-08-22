import numpy as np
from math import sin, cos, pi, sqrt, atan2, asin
from glob import glob
from PIL import Image
Image.MAX_IMAGE_PIXELS = None  #avoid decompression bomb warning

import rasterio
import pyproj
from tqdm import tqdm
import matplotlib.pyplot as plt
from scipy.spatial import Delaunay

from memory_profiler import profile

#use geolocated images to create texture and vertex coordinates for each satellite on the sphere
class TiffImage():
    def __init__(self, satellite : str, resolution : str):
        self.satellite = satellite
        self.resolution = resolution
        self.file = glob(f'images/{satellite}/{resolution}/{satellite}*.tif')[0]
        self._load_image()
        self.wgs84 = pyproj.Proj(proj='latlong', datum='WGS84')
        #lonlat transformer turns longitude/latitude coordinates into geostationary coordinates
        self.lonlat_transformer = pyproj.Transformer.from_proj(self.wgs84, self.projection, always_xy=True)
        #geos transformer turns geostationary coordinates into longitude/latitude coordinates
        self.geos_transformer = pyproj.Transformer.from_proj(self.projection, self.wgs84, always_xy=True)
        self.rows, self.cols = self.image.shape
          
        self._load_obj('models/ico_6div.obj')
        self._initialize_vertex_lon_lat()
        self._texcoord_lookup()

    def _load_image(self):
        file = self.file
        src = rasterio.open(file)
        self.image = src.read(1)
        self.image_arr = np.asarray(Image.open(file))

        self.transform = src.transform
        self.projection = pyproj.Proj(src.crs, datum='WGS84')
        self.src = src

    #loads the vertices and indices from an obj file
    def _load_obj(self, filepath) -> None:
        vertices = []
        indices = []

        with open(filepath, 'r') as f:
            for line in f:
                if line.startswith('v '):
                    vertex = line.split()[1:]
                    vertices.append(vertex)
                elif line.startswith('f '):
                    face = line.split()[1:]
                    for i in range(3):
                        indices.append(face[i].split('/')[0])
        
        self.vertices = np.array(vertices, dtype=np.float32)
        self.indices = np.array(indices, dtype=np.uint32) - np.ones(len(indices), dtype=np.uint32)
        self.length = len(self.indices)

    def _initialize_vertex_lon_lat(self):
        vertex_lon_lat = []
        for vertex in self.vertices:
            lon, lat = self.world_to_latlon(vertex[0], vertex[1], vertex[2]) #make sure the radius is correct
            vertex_lon_lat.append([lon, lat])

        self.vertex_lon_lat = np.array(vertex_lon_lat)

    def world_to_latlon(self, x, y, z):
        R = sqrt(x**2 + y**2 + z**2)
        #convert coordinates on the sphere to longitude and latitude
        lat = asin(z / R) 
        lon = atan2(y, x)

        #convert radians to degrees
        lat = (lat * (180 / pi))
        lon = lon * (180 / pi)

        return lon, lat
    
    def _texcoord_lookup(self):
        #convert lat lon from vertices to geostationary coordinates
        x_geos, y_geos = self.lonlat_transformer.transform(self.vertex_lon_lat[:, 0], self.vertex_lon_lat[:, 1])

        #remove invalid coordinates
        valid_mask_inf = ~np.logical_or(np.isinf(x_geos), np.isinf(y_geos))
        valid_mask_nan = ~np.logical_or(np.isnan(x_geos), np.isnan(y_geos))
        valid_mask = np.logical_and(valid_mask_inf, valid_mask_nan)

        x_geos = x_geos[valid_mask]
        y_geos = y_geos[valid_mask]
        self.vertices = self.vertices[valid_mask]

        #convert to pixel coordinates
        row, col = self.src.index(x_geos, y_geos)
        #normalize the coordinates
        row = np.array(row) / self.rows
        col = np.array(col) / self.cols
        
        self.tex_coords = np.column_stack((col, row))
        self.geos_coords = np.column_stack((x_geos, y_geos))
        self.vertex_lon_lat = self.vertex_lon_lat[valid_mask]

    def _get_img_coords(self):
        print('Calculating image coordinates...')
        #get the geos coords of each pixel in the image
        x, y = np.meshgrid(np.arange(self.cols), np.arange(self.rows))

        x_geos, y_geos = self.src.xy(x.ravel(), y.ravel())
        combined_array = np.column_stack((x_geos, y_geos))

        return combined_array

    def _create_invalid_mask(self):
        lon, lat = self.geos_transformer.transform(self.image_coords[:, 0], self.image_coords[:, 1])
        invalid_mask = np.logical_or(np.isinf(lon), np.isinf(lat))

        self.invalid_mask = invalid_mask

    def save(self):
        np.save(f'data/texture_coords/{self.satellite}_tex_coords.npy', self.tex_coords.flatten().astype(np.float32))
        np.save(f'data/vertex_coords/{self.satellite}_vertex_coords.npy', self.vertices.flatten().astype(np.float32))


#the following functions will define a novel method for blending the images together based
#on the vertices that lie on each image.
class ImageBlender():
    def __init__(self, satellite1 : str, satellite2 : str, resolution : str) -> None:
        self.satellite = satellite1
        self.resolution = resolution
        self.adjacent_satellite = satellite2
        self.data = TiffImage(self.satellite, resolution)
        self.neighbor_data = TiffImage(satellite2, resolution)
        
        #determine which vertices are shared between the images
        self._get_overlapping_vertices()

        #calculate the weight of each vertex based on the distance between the points
        #and the two satellites
        self._get_vertex_weights() 

        #triangulate takes the vertex pixel coordinates and uses the pixel barycentric coordinates
        #for each triangle to determine the weight of each pixel in each triangle as well as the 
        #'twin' pixel location in the neighboring satellite image
        self._triangulate()

        #saves the generated data to an image of shape (x, y, 3) where x and y are the dimensions of the 
        #main image, (x, y, 0) is the pixel weight, (x, y, 1) is the x coordinate of the twin pixel, and
        #(x, y, 2) is the y coordinate of the twin pixel. All blending information is stored in this image
        self._save_blending_image()

    def _get_overlapping_vertices(self) -> None:
        my_tex_coords = []

        vertex_lon_lats = self.data.vertex_lon_lat
        n_verts = self.neighbor_data.vertex_lon_lat

        n_mask = np.logical_and(np.isin(n_verts[:, 0], vertex_lon_lats[:, 0]),
                                np.isin(n_verts[:, 1], vertex_lon_lats[:, 1]))
        neighbor_vertices = n_verts[n_mask]

        #convert vertex lon/lat to geostationary coordinates
        #get the geostationary coordinates of the vertices for the main image
        my_geos_x, my_geos_y = self.data.lonlat_transformer.transform(neighbor_vertices[:, 0], neighbor_vertices[:, 1])
        #get the geostationary coordinates of the vertices for the neighboring image
        n_geos_x, n_geos_y = self.neighbor_data.lonlat_transformer.transform(neighbor_vertices[:, 0], neighbor_vertices[:, 1])

        #convert geostationary coordinates to pixel coordinates for both images
        my_tc_x, my_tc_y = self.data.src.index(my_geos_x, my_geos_y)
        n_tc_x, n_tc_y = self.neighbor_data.src.index(n_geos_x, n_geos_y)

        neighbor_tex_coords = np.column_stack((n_tc_x, n_tc_y))
        my_tex_coords = np.column_stack((my_tc_x, my_tc_y))

        self.overlapping_vertices = neighbor_vertices
        self.neighboring_tex_coords = neighbor_tex_coords
        self.vertex_coords = my_tex_coords

    def _get_vertex_weights(self) -> None:
        #vertex weights should be between 0 and 1, and calculated based on the weighted difference between
        #the longitude/latitude difference between vertex and satellites

        #calculate the weights for each vertex
        sat_lon0 = np.radians(self.data.projection.crs.to_dict()['lon_0']) + pi #normalize to [0, 2pi]
        neighbor_lon0 = np.radians(self.neighbor_data.projection.crs.to_dict()['lon_0']) + pi
        sat_lat0 = 0.0 #geostationary satellite latitude is always 0 

        v_lons = np.radians(self.overlapping_vertices[:, 0]) + pi
        v_lats = np.radians(self.overlapping_vertices[:, 1])

        my_dists = ImageBlender._haversine_distance(sat_lat0, sat_lon0, v_lats, v_lons)
        n_dists = ImageBlender._haversine_distance(sat_lat0, neighbor_lon0, v_lats, v_lons)

        #clip max distance to center
        sat_dist = ImageBlender._haversine_distance(sat_lat0, sat_lon0, sat_lat0, np.array([neighbor_lon0]))[0]
        min_distance = np.min(np.concatenate([my_dists, n_dists]))

        #where the distance is less than the min distance, set the distance to the min distance
        my_dists[n_dists > sat_dist] = min_distance
        n_dists[my_dists > sat_dist] = min_distance

        #where the distance is greater than the max distance, set the distance to the max distance
        n_dists[n_dists > sat_dist] = sat_dist
        my_dists[my_dists > sat_dist] = sat_dist

        #normalize them
        norm_my_dist = my_dists / sat_dist 
        norm_n_dist = n_dists / sat_dist
        #calculate the ratio so that each image is on the same page with regard to the blend value
        ratio = norm_n_dist / (norm_my_dist + norm_n_dist)

        self.vertex_weights = ratio

    def _haversine_distance(lat1 : float, lon1 : float, lat2 : np.ndarray, lon2 : np.ndarray) -> np.ndarray:
        #handle the -180 180 degree boundary
        #since we converted to 0-2pi, the critical values become pi/2 and 3pi/2
        #if the first point is below 90 degrees, convert any lon2 points less than -90 degrees to negative values from 0
        if (lon1 < pi / 2.0):
            lon2[lon2 > (3 * pi) / 2.0] = [-((2 * pi) - i) for i in lon2[lon2 > (3 * pi) / 2.0]]
            print(lon2[lon2 < -pi / 2.0])

        #if the first point is less than -90 degrees, convert these points to negative values from 0 along with all lon2 points that need
        #conversion too
        if (lon1 > (3 * pi) / 2.0):
            lon1 = -((2 * pi) - lon1) #distance to zero of lon1
            lon2[lon2 > ((3 * pi) / 2.0)] = [-((2 * pi) - i) for i in lon2[lon2 > ((3 * pi) / 2.0)]]

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
        c = 2 * np.arcsin(np.sqrt(a))
        r = 1.0  # dummy value

        return np.array(abs(dlon) * r) #only return the longitudinal distance for now

    #this function uses a lot of memory, so it may actually kill your computer for a moment if you have less
    # than 16 GB of memory and you try to use it on high res (>11,000x11,000 px) images.
    #I don't think it's a memory leak, it's just a lot of data.
    def _triangulate(self):
        tex_coords = self.vertex_coords
        self.triangulation = Delaunay(tex_coords)
        triangles = self.triangulation.simplices

        n_pixel_coords = self.neighboring_tex_coords
        weights = self.vertex_weights

        triangle_pixels = []   #pixel coordinates for each triangle
        n_triangle_pixels = [] #pixel coordinates for each triangle in the neighboring image
        triangle_weights = []  #pixel weights for each triangle

        with tqdm(total=len(triangles), desc='Triangulating...') as pbar:
            for triangle in triangles:
                pixels, n_pixels, pixel_weights = self.get_pixels_for_triangle(triangle, tex_coords, n_pixel_coords, weights)
                
                triangle_pixels.append(pixels)
                n_triangle_pixels.append(n_pixels)
                triangle_weights.append(pixel_weights)
                
                pbar.update(1)
        
        self.triangulated_pixels = np.concatenate(triangle_pixels)
        self.triangulated_n_pixels = np.concatenate(n_triangle_pixels)
        self.triangulated_weights = np.concatenate(triangle_weights)

    def get_pixels_for_triangle(self, triangle, pixel_coords, n_pixel_coords, vertex_weights) -> list:
        #get the vertices of the triangle
        vertices = np.array([pixel_coords[triangle[i]] for i in range(3)]) #pixel locations of the vertices
        n_vertices = np.array([n_pixel_coords[triangle[i]] for i in range(3)]) #pixel locations of the vertices in the neighboring image
        weight_vals = np.array([vertex_weights[triangle[i]] for i in range(3)])

        #calculate the bounding box of the triangle
        min_x = int(np.min(vertices[:, 0]))
        max_x = int(np.max(vertices[:, 0]))
        min_y = int(np.min(vertices[:, 1]))
        max_y = int(np.max(vertices[:, 1]))

        #generate the array of pixels within the bounding box
        pixel_weights = []

        # Generate x and y bounding box coordinates
        x_coords = np.arange(min_x - 1, max_x + 1)
        y_coords = np.arange(min_y - 1, max_y + 1)
        x_mesh, y_mesh = np.meshgrid(x_coords, y_coords)
        pixel_coords = np.column_stack((x_mesh.ravel(), y_mesh.ravel()))

        center_x = vertices[:, 0].mean() #determine the simplex using the center of the triangle
        center_y = vertices[:, 1].mean()
        center = np.array([center_x, center_y])
        simplex = self.triangulation.find_simplex(center)

        #calculate the barycentric coordinates of each pixel
        coords = self._calculate_barycentric_coords(pixel_coords, simplex)
        valid_indices = np.logical_and(np.all(coords >= 0, axis=1), np.all(coords <= 1, axis=1))
        coords = coords[valid_indices]
        pixel_coords = pixel_coords[valid_indices]
        
        #compute the weighted sum of vertex weights.
        pixel_weights = np.sum(coords * weight_vals, axis=1)

        #calculate the neighboring pixel coordinates
        n_pixel_coords = np.round(np.sum(coords[:, :, np.newaxis] * n_vertices[np.newaxis, :, :], axis=1)).astype(np.int32)

        return pixel_coords, n_pixel_coords, pixel_weights

    def _calculate_barycentric_coords(self, points, simplex):
        simp = self.triangulation

        b0 = (simp.transform[[simplex], :points.shape[1]].transpose([1, 0, 2]) *
            (points - simp.transform[[simplex], points.shape[1]])).sum(axis=2).T
        coords = np.c_[b0, 1 - b0.sum(axis=1)]

        return coords
        
    def _save_blending_image(self):
        #convert pixels and associated weights into an image the same size as the original
        x = self.data.cols
        y = self.data.rows

        image = np.zeros((x, y, 3))

        image[self.triangulated_pixels[:, 0], self.triangulated_pixels[:, 1], 0] = self.triangulated_weights
        image[self.triangulated_pixels[:, 0], self.triangulated_pixels[:, 1], 1] = self.triangulated_n_pixels[:, 0]
        image[self.triangulated_pixels[:, 0], self.triangulated_pixels[:, 1], 2] = self.triangulated_n_pixels[:, 1]

        image = image.reshape(x, y, 3)

        print('Saving blending image...')
        np.save(f'images/blending_masks/{self.resolution}/{self.satellite}_{self.adjacent_satellite}.npy', image)