import os
import os.path as osp
import argparse
import xml.etree.ElementTree as ET
import re
import copy
from typing import List

import tifffile as tif
import yaml


# --------- METADATA PROCESSING -----------

def get_first_element_of_dict(dictionary: dict):
    dict_keys = list(dictionary.keys())
    first_key = dict_keys[0]
    return dictionary[first_key]


def digits_from_str(string: str):
    return [int(x) for x in re.split(r'(\d+)', string) if x.isdigit()]


def get_metadata_from_cycle_map_file(cycle_map_file_path: str):
    with open(cycle_map_file_path, 'r') as s:
        cycle_map = yaml.safe_load(s)
    return cycle_map


def process_cycle_map(cycle_map: dict):
    cycle_names = list(cycle_map.keys())
    cycle_ids = [digits_from_str(name)[0] for name in cycle_names]
    new_cycle_map = dict()
    for i in range(0, len(cycle_ids)):
        this_cycle_name = cycle_names[i]
        this_cycle_id = cycle_ids[i]
        new_cycle_map[this_cycle_id] = cycle_map[this_cycle_name]

    # sort keys
    sorted_keys = sorted(new_cycle_map.keys())
    processed_cycle_map = dict()
    for k in sorted_keys:
        processed_cycle_map[k] = new_cycle_map[k]

    return processed_cycle_map


def get_image_dims(path: str):
    with tif.TiffFile(path) as TF:
        image_shape = list(TF.series[0].shape)
        image_dims = list(TF.series[0].axes)
    dims = ['Z', 'Y', 'X']
    image_dimensions = dict()
    for d in dims:
        if d in image_dims:
            idx = image_dims.index(d)
            image_dimensions[d] = image_shape[idx]
        else:
            image_dimensions[d] = 1
    return image_dimensions


def get_dimensions_per_cycle(cycle_map: dict):
    dimensions_per_cycle = dict()
    for cycle in cycle_map:
        this_cycle_channels = cycle_map[cycle]
        this_cycle_channels_paths = list(this_cycle_channels.values())
        num_channels = len(this_cycle_channels_paths)
        first_channel_dims = get_image_dims(this_cycle_channels_paths[0])
        num_z_planes = 1 if first_channel_dims['Z'] == 1 else first_channel_dims['Z'] * num_channels
        this_cycle_dims = {'SizeT': 1,
                           'SizeZ': num_z_planes,
                           'SizeC': num_channels,
                           'SizeY': first_channel_dims['Y'],
                           'SizeX': first_channel_dims['X']
                           }
        dimensions_per_cycle[cycle] = this_cycle_dims
    return dimensions_per_cycle


def generate_channel_meta(channel_names: List[str], cycle_id: int, offset: int):
    channel_elements = []
    for i, ch in enumerate(channel_names):
        new_channel_name = 'c' + format(cycle_id, '02d') + ' ' + ch
        channel_attrib = {'ID': 'Channel:0:' + str(offset + i), 'Name': new_channel_name, 'SamplesPerPixel':"1"}
        channel = ET.Element('Channel', channel_attrib)
        channel_elements.append(channel)
    return channel_elements


def generate_tiffdata_meta(image_dimensions: dict):
    tiffdata_elements = []
    ifd = 0
    for t in range(0, image_dimensions['SizeT']):
        for c in range(0, image_dimensions['SizeC']):
            for z in range(0, image_dimensions['SizeZ']):
                tiffdata_attrib = {'FirstT': str(t), 'FirstC': str(c), 'FirstZ': str(z), 'IFD': str(ifd)}
                tiffdata = ET.Element('TiffData', tiffdata_attrib)
                tiffdata_elements.append(tiffdata)
                ifd += 1
    return tiffdata_elements


def image_dimensions_combined_for_all_cycles(image_dimensions_per_cycle: dict):
    combined_dimensions = dict()
    dimensions_that_change_in_cycles = ['SizeT', 'SizeZ', 'SizeC']
    num_cycles = len(list(image_dimensions_per_cycle.keys()))
    first_cycle = get_first_element_of_dict(image_dimensions_per_cycle)
    for dim in dimensions_that_change_in_cycles:
        this_dim_value = first_cycle[dim]
        if this_dim_value == 1:
            combined_dim_value = 1
        else:
            combined_dim_value = this_dim_value * num_cycles

        combined_dimensions[dim] = combined_dim_value
    combined_dimensions['SizeY'] = first_cycle['SizeY']
    combined_dimensions['SizeX'] = first_cycle['SizeX']

    return combined_dimensions


def generate_default_pixel_attributes(image_path: str):
    with tif.TiffFile(image_path) as TF:
        img_dtype = TF.series[0].dtype

    pixels_attrib = {'ID': 'Pixels:0', 'DimensionOrder': 'XYCZT', 'Interleaved': 'false', 'Type': img_dtype.name}
    return pixels_attrib


def generate_combined_ome_meta(cycle_map: dict, image_dimensions: dict, pixels_attrib: dict):
    proper_ome_attrib = {'xmlns': 'http://www.openmicroscopy.org/Schemas/OME/2016-06',
                         'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                         'xsi:schemaLocation': 'http://www.openmicroscopy.org/Schemas/OME/2016-06 http://www.openmicroscopy.org/Schemas/OME/2016-06/ome.xsd'}

    channel_id_offset = 0
    channel_elements = []
    for i, cycle in enumerate(cycle_map):
        channel_names = cycle_map[cycle]
        num_channels = len(channel_names)
        this_cycle_channels = generate_channel_meta(channel_names, cycle, channel_id_offset)
        channel_elements.extend(this_cycle_channels)
        channel_id_offset += num_channels
    tiffdata_elements = generate_tiffdata_meta(image_dimensions)

    for key, val in image_dimensions.items():
        image_dimensions[key] = str(val)

    pixels_attrib.update(image_dimensions)

    node_ome = ET.Element('OME', proper_ome_attrib)
    node_image = ET.Element('Image', {'ID': 'Image:0', 'Name': 'default.tif'})
    node_pixels = ET.Element('Pixels', pixels_attrib)

    for ch in channel_elements:
        node_pixels.append(ch)

    for td in tiffdata_elements:
        node_pixels.append(td)

    node_image.append(node_pixels)
    node_ome.append(node_image)

    xmlstr = ET.tostring(node_ome, encoding='utf-8', method='xml').decode('ascii')
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>'
    ome_meta = xml_declaration + xmlstr

    return ome_meta


def generate_separated_ome_meta(cycle_map: dict, image_dimensions_per_cycle: dict, pixels_attrib: dict):
    ome_meta_per_cycle = dict()
    for cycle in cycle_map:
        this_cycle_image_dimensions = copy.deepcopy(image_dimensions_per_cycle[cycle])
        this_cycle_cycle_map = {cycle: cycle_map[cycle]}
        this_cycle_ome_meta = generate_combined_ome_meta(this_cycle_cycle_map, this_cycle_image_dimensions, pixels_attrib)
        ome_meta_per_cycle[cycle] = this_cycle_ome_meta

    return ome_meta_per_cycle

# ------- IMAGE PROCESSING ------------

def save_cycles_combined_into_one_file(cycle_map: dict, out_dir: str, ome_meta: str):
    file_name = 'cycles_combined.tif'
    out_path = osp.join(out_dir, file_name)

    with tif.TiffWriter(out_path, bigtiff=True) as TW:
        for cycle, channels in cycle_map.items():
            for channel_path in channels.values():
                TW.save(tif.imread(channel_path), photometric='minisblack', description=ome_meta)


def save_cycle(input_path_list: List[str], out_path: str, ome_meta: str):
    with tif.TiffWriter(out_path, bigtiff=True) as TW:
        for path in input_path_list:
            TW.save(tif.imread(path),  photometric='minisblack', description=ome_meta)


def save_cycles_separated_per_file(cycle_map: dict, out_dir: str, ome_meta_per_cycle: dict):
    for cycle, channels in cycle_map.items():
        channel_paths = channels.values()
        ome_meta = ome_meta_per_cycle[cycle]
        file_name = 'cycle{cycle:02d}.tif'.format(cycle=cycle)
        out_path = osp.join(out_dir, file_name)
        save_cycle(channel_paths, out_path, ome_meta)


def main(cycle_map_file_path: str, out_dir: str, param: str):

    if not osp.exists(out_dir):
        os.makedirs(out_dir)

    print('Creating OME metadata')
    cycle_map = get_metadata_from_cycle_map_file(cycle_map_file_path)
    processed_cycle_map = process_cycle_map(cycle_map)

    first_cycle_channels = get_first_element_of_dict(processed_cycle_map)
    first_channel_path = list(first_cycle_channels.values())[0]

    pixels_attrib = generate_default_pixel_attributes(first_channel_path)
    image_dimensions_per_cycle = get_dimensions_per_cycle(processed_cycle_map)

    print('Processing images')
    if param == 'combine':
        image_dimensions = image_dimensions_combined_for_all_cycles(image_dimensions_per_cycle)
        ome_meta = generate_combined_ome_meta(processed_cycle_map, image_dimensions, pixels_attrib)
        save_cycles_combined_into_one_file(processed_cycle_map, out_dir, ome_meta)
    elif param == 'separate':
        ome_meta_per_cycle = generate_separated_ome_meta(processed_cycle_map, image_dimensions_per_cycle, pixels_attrib)
        save_cycles_separated_per_file(processed_cycle_map, out_dir, ome_meta_per_cycle)
    else:
        raise ValueError('Incorrect value for argument -p, allowed options: separate, combine')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', type=str, help='path to cycle map file YAML')
    parser.add_argument('-o', type=str, help='directory to output combined images')
    parser.add_argument('-p', type=str, help='parameters how to bundle images: separate, combine. ' +
                                             'separate - each cycle in a separate file, ' +
                                             'combine - all cycles combined in one file')

    args = parser.parse_args()

    main(args.m, args.o, args.p)
