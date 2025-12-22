"""SXM Scan/Spec Readers.

This code is based off of the logic in SciFiReaders at:

SciFiReaders.readers.microscopy.spm.afm import pifm

(particularly, our base commit was 1384e51)

However, we noticed that the pifm reader in this package does not
match the data as it is saved on our system.
"""

import os
import glob
from dataclasses import dataclass
from typing import Any
from types import MappingProxyType  # Immutable dict
import numpy as np
from sidpy import sid


# ----- Scan Reading Main ----- #
SCAN_DATA_EXT = '.int'
SCAN_METADATA_EXT = '.txt'
SPEC_DATA_EXT = '.dat'
SCAN_METADATA_BEGIN = 'FileDescBegin'
RES_X = 'xPixel'
RES_Y = 'yPixel'
RANGE_X = 'XScanRange'
RANGE_Y = 'YScanRange'
CENTER_X = 'xCenter'
CENTER_Y = 'yCenter'
UNIT_X = 'XPhysUnit'
UNIT_Y = 'YPhysUnit'


# Stored metadata
MD_SCAN_FILENAME = 'Filename'
MD_SCAN_CAPTION = 'Caption'
MD_SCAN_UNITS = 'Physical_Units'


@dataclass
class ScanInfo:
    """Scan-specific metadata stored in the metadata file."""

    filename: str
    caption: str
    scale: float
    phys_unit: str
    offset: float


def read_scan(metadata_path: str) -> [sid.Dataset]:
    """Load a 2D scan given the path to its metadata file.

    The metadata file is a .txt file. There is a .int data file for each
    scan channel.

    Args:
        metadata_path: path to the metadata file.

    Returns:
        A list of sidpy Datasets, where each Dataset corresponds to a
            channel of the scan.
    """
    metadata = _read_anfatec_params(metadata_path)
    dim0, dim1 = _make_dimensions(metadata)
    scans, scan_infos = _read_scan_data(metadata_path, metadata)

    dsets = []
    for scan, scan_info in zip(scans, scan_infos):
        dset = sid.Dataset.from_array(scan, name=scan_info.caption)
        dset.data_type = 'Image'
        dset.set_dimension(0, dim0)
        dset.set_dimension(1, dim1)
        dset.units = scan_info.phys_unit
        dset.quantity = scan_info.caption
        dset.original_metadata = metadata
        dset.original_metadata.update({MD_SCAN_FILENAME: scan_info.filename,
                                       MD_SCAN_CAPTION: scan_info.caption,
                                       MD_SCAN_UNITS: scan_info.phys_unit})
        dsets.append(dset)
    return dsets


class SXMScanReader(sid.Reader):
    """Reads Omicron SXM Scan files.

    We expect the provided file_path to correspond to the associated
    metadata file (.txt file). We load the 2D scans indicated by it
    and return them via the read method.
    """

    def read(self) -> [sid.Dataset]:
        """Read file path provided in constructor and return read scans."""
        self.datasets = read_scan(self._input_file_path)
        return self.datasets


# ----- Spec Reading Main ----- #
MD_PREFIX = ';'
MD_KEY_VAL_DELINEATOR = ':'
KEY_PROBE_POS_XY = 'x/y-Pos'
SPEC_DATA_SEP = '\t'


# Stored metadata
MD_PROBE_POS_X = 'x-Pos'
MD_PROBE_POS_Y = 'y-Pos'
MD_POS_UNITS = 'nm'


# Mapping of data to units, as this is not stored in the spec file.
SPEC_NAME_TO_UNIT_MAP = MappingProxyType({
    'time': 's',
    'dz': 'nm',
    'Bias': 'mV',
    'It_to_PC': 'A'})
# TODO: Complete me!


def read_spec(spec_path: str) -> [sid.Dataset]:
    """Load a single-point spectroscopy given the path to it.

    Args:
        spec_path: path to the single-point spectroscopy file (.dat file).

    Returns:
        A list of sidpy Datasets, where each Dataset corresponds to a signal
            of the spectroscopy.
    """
    with open(spec_path, 'r') as file:
        lines = file.readlines()

    raw_md = _extract_raw_spec_metadata(lines)
    md = _parse_useful_spec_metadata(raw_md)
    names, data = _extract_spec_data(lines)
    units = [SPEC_NAME_TO_UNIT_MAP[name] for name in names]

    # Split data along columns
    data_cols = np.moveaxis(data, 1, 0)

    # Using the first data column as our dim.
    # NOTE: For Asylum, it uses 'dz' or 'Raw' and throws an
    # exception otherwise.
    # Here, I'm just sticking with the first col to be safe.
    dim = sid.Dimension(data_cols[0], name=names[0],
                        units=units[0], quantity=names[0])

    # Pretty simplistic 'dimension', just indices.
#    dim = sid.Dimension(np.arange(data[0].shape[0]),
#                        name='Index')

    datasets = []
    for name, unit, data in zip(names, units, data_cols):
        dset = sid.Dataset.from_array(data, name=name)
        dset.data_type = 'spectrum'
        dset.units = unit
        dset.quantity = name
        dset.original_metadata = md
        dset.set_dimension(0, dim)

        datasets.append(dset)
    return datasets


class SXMSpecReader(sid.Reader):
    """Reads Omicron SXM Single-Spectroscopy files.

    We expect the provided file_path to correspond to the associated
    spec file (.dat file). We load the specs indicated by it
    and return them via the read method.
    """

    def read(self) -> [sid.Dataset]:
        """Read file path provided in constructor and return read specs."""
        self.datasets = read_spec(self._input_file_path)
        return self.datasets


# ----- Scan Reading Private Methods ----- #
def _read_anfatec_params(metadata_path: str) -> dict[str, Any]:
    """Read the scan metadata and writes them to a dictionary."""
    params_dictionary = {}
    params = True
    with open(metadata_path, 'r', encoding="ISO-8859-1") as f:
        for line in f:
            if params:
                sline = [val.strip() for val in line.split(':')]
                if len(sline) == 2 and sline[0][0] != ';':
                    params_dictionary[sline[0]] = sline[1]
                # in ANFATEC parameter files, all attributes are written before
                # file references.
                if sline[0].startswith(SCAN_METADATA_BEGIN):
                    params = False
        f.close()
    return params_dictionary


def _read_scan_infos(metadata_path: str) -> dict[str, ScanInfo]:
    """Extract ScanInfo metadata from metadata file."""
    img_desc = {}

    with open(metadata_path, 'r', encoding="ISO-8859-1") as f:
        lines = f.readlines()
        for index, line in enumerate(lines):
            sline = [val.strip() for val in line.split(':')]

            # if true, then file describes image.
            if sline[0].startswith(SCAN_METADATA_BEGIN):
                no_descriptors = 5
                file_desc = []

                for i in range(no_descriptors):
                    line_desc = [val.strip()
                                 for val in lines[index+i+1].split(':')]
                    file_desc.append(line_desc[1])  # val in key:val

                # Only store metadata for scans.
                # (We should not be getting any for specs, this is weird
                # outdated behaviour).
                if os.path.splitext(file_desc[0])[1] == SCAN_DATA_EXT:
                    info = ScanInfo(*file_desc)
                    info.scale = float(info.scale)
                    info.offset = float(info.offset)
                    img_desc[file_desc[0]] = info
    return img_desc


def _get_scan_paths(metadata_path: str) -> [str]:
    """Given a scan metadata path, output associated scan file paths."""
    metadata_dir = os.path.dirname(metadata_path)
    # Get filename prefix without extension
    prefix = os.path.splitext(os.path.basename(metadata_path))[0]
    paths = glob.glob(metadata_dir + os.sep + prefix + "*"
                      + SCAN_DATA_EXT)
    return paths


def _read_scan_data(metadata_path: str,
                    metadata: dict[str, Any]
                    ) -> (list[np.ndarray], list[ScanInfo]):
    """Read scan data for various channels.

    Args:
        metadata_path: path to the metadata.
        metadata: loaded metadata.

    Returns:
        (scans, scan_infos) tuple of:
        scans: the loaded scans.
        scan_infos: associated ScanInfos.
    """
    scan_paths = _get_scan_paths(metadata_path)
    scan_base_names = [os.path.basename(scan_path) for scan_path in scan_paths]
    scan_infos_dict = _read_scan_infos(metadata_path)

    # If they don't match, something wonky is up!
    print(scan_paths)
    print(scan_infos_dict.keys())
    assert scan_base_names == list(scan_infos_dict.keys())

    # Get resolution
    res_x = int(metadata[RES_X])
    res_y = int(metadata[RES_Y])

    scans = []
    for filename, scan_info in scan_infos_dict.items():
        file_path = os.path.join(os.path.dirname(metadata_path), filename)
        scan = np.fromfile(file_path,
                           dtype='i4').astype(float)  # Convert to float
        scan = np.reshape(scan, (res_x, res_y))  # Reshape to 2D shape
        scan = scan * scan_info.scale - scan_info.offset  # y = mx - b
        #scans_dict[filename] = scan
        scans.append(scan)
    return scans, list(scan_infos_dict.values())


def _make_dimensions(metadata: dict[str, Any]
                     ) -> (sid.Dimension, sid.Dimension):
    x_range = float(metadata[RANGE_X])
    y_range = float(metadata[RANGE_Y])
    x_center = float(metadata[CENTER_X])
    y_center = float(metadata[CENTER_Y])

    x_start = x_center - (x_range / 2)
    x_end = x_center + (x_range / 2)
    y_start = y_center - (y_range / 2)
    y_end = y_center + (y_range / 2)

    dx = x_range / float(metadata[RES_X])
    dy = y_range / float(metadata[RES_Y])

    # assumes y scan direction:down; scan angle: 0 deg
    y_linspace = -np.arange(y_start, y_end, step=dy)
    x_linspace = np.arange(x_start, x_end, step=dx)

    # Get x/y units. Replace mu with u (if necessary).
    x_unit = metadata[UNIT_X].replace('\xb5', 'u')
    y_unit = metadata[UNIT_Y].replace('\xb5', 'u')

    dim0 = sid.Dimension(x_linspace, name='x', units=x_unit,
                         dimension_type='spatial', quantity='Length')
    dim1 = sid.Dimension(y_linspace, name='y', units=y_unit,
                         dimension_type='spatial', quantity='Length')
    return dim0, dim1


# ----- Reading Single-Spectroscopy Methods ----- #
def _extract_raw_spec_metadata(lines: list[str]) -> dict[str, str]:
    """Extract metadata from spec file lines into dict.

    Given the read lines from a spectroscopy file, extract the raw metadata
    and return it as a dict of metadata key and vals (both str).

    This metadata is of the format:
        ;KEY_A/KEY_B: VAL_A/VAL_B

    However, the formatting is such that, KEY_A and KEY_B may have a common
    substring that is only included in one of them. Thus, it is non-trivial
    to properly split them up. Because of this, this method treats each
    line as an individual key:val pair, even if most are actually 'composite'
    key:val pairs.

    This method will extract the keys as independent attributes, with the full
    val string (consisting of various sub keys) stored as a metadata element.

    Args:
        lines: list[str] of read lines from a spectroscpy file.

    Returns:
        str:str key:val dict containing MD_KEY:MD_STR.
    """
    # Strip newlines from every line
    md_lines = [line[1:].rstrip() for line in lines if line[0] == MD_PREFIX]
    raw_md = {}
    for line in md_lines:
        kv = line.split(MD_KEY_VAL_DELINEATOR)
        k = kv[0].strip()
        v = kv[1].strip()
        raw_md[k] = v
    return raw_md


def _parse_useful_spec_metadata(raw_md: dict[str, str]) -> dict[str, str]:
    """Parse raw metadata and extract some useful metadata.

    Particularly, we want to explicit:
    - Probe Position (x,y) where the spec file was collected, stored with
        KEY_PROBE_POS_XY.

    Args:
        raw_md: raw metadata extracted from spec file.

    Returns:
        new dict containing the parsed 'useful' data, with keys matching
            those indicated above.
    """
    xy_vals = raw_md[KEY_PROBE_POS_XY]
    x_val, y_val = xy_vals.split('/')
    raw_md[MD_PROBE_POS_X] = float(x_val)
    raw_md[MD_PROBE_POS_Y] = float(y_val)
    return raw_md


def _extract_spec_data(lines: list[str]) -> (list[str], list[str], np.ndarray):
    r"""Extract data from spec file lines into names and data.

    Given the read lines from a spectroscopy file, extract the data (as a
    numpy array) and the channel names (as a list of strings).

    The data if stored in this format:
        time\tdz\tBias\tIt_to_PC
        +5.992000E-003\t+0.000000E+000\t-8.501130E-005\t-3.887102E-012
        [...]

    We extract the channel names from the 1st line.
    We extract all data between the 2nd line and the end.

    Args:
        lines: list[str] of read lines from a spectroscpy file.

    Returns:
        (list[str], np.ndarray) of:
        - list[str] of channel names
        - np.ndarray of all data.
    """
    lines = lines[1:]  # Skip first line, which should be always empty
    # rstrip() to remove newlines at end of lines
    lines = [line.rstrip() for line in lines if line[0] != MD_PREFIX]

    # Get channel names
    names = lines[0].split(SPEC_DATA_SEP)

    # Get data
    data = [[val for val in line.split(SPEC_DATA_SEP)] for line in lines[1:]]
    data = np.array(data, dtype=float)

    return names, data
