"""Tests SXM scan/spec reader."""

import pytest
import logging
from os import sep
from pathlib import Path

import numpy as np

from afspm.components.microscope.translators.omicronsxm import reader as reader_sxm


logger = logging.getLogger(__name__)


BASE_PATH = str(Path(__file__).parent.parent.resolve())


@pytest.fixture
def spec_path():
    return (BASE_PATH + sep + '..' + sep + '..' + sep +
            'data' + sep + 'dummy_file0000.dat')


@pytest.fixture
def spec_raw_data_first():
    return [5.992000e-003, 0.000000e+000, -8.501130e-005, -3.887102e-012]


@pytest.fixture
def spec_raw_data_last():
    return [1.029960e+001, 0.000000e+000, -8.501130e-005, -3.943999e-012]


@pytest.fixture
def xy_pos():
    return 0.25


@pytest.fixture
def names():
    return ['time', 'dz', 'Bias', 'It_to_PC']


def test_read_spec(spec_path, spec_raw_data_first, spec_raw_data_last,
                   names, xy_pos):
    reader = reader_sxm.SXMSpecReader(spec_path)
    datasets = reader.read()

    for idx, ds in enumerate(datasets):
        # Assert first and last values make sense
        assert spec_raw_data_first[idx] == datasets[idx].compute()[0]
        assert spec_raw_data_last[idx] == datasets[idx].compute()[-1]

        # Assert X-Pos and Y-Pos are right
        assert (datasets[idx].original_metadata[reader_sxm.MD_PROBE_POS_X]
                == xy_pos)
        assert (datasets[idx].original_metadata[reader_sxm.MD_PROBE_POS_Y]
                == xy_pos)

        # Assert names are stored
        assert names[idx] == datasets[idx].quantity


@pytest.fixture
def scan_md_path():
    return (BASE_PATH + sep + '..' + sep + '..' + sep +
            'data' + sep + 'dummy_file00.txt')


@pytest.fixture
def channels():
    return ['It_to_PCFwd', 'It_to_PCBwd']


@pytest.fixture
def units():
    return ['A', 'A']


@pytest.fixture
def scan_first_vals():

    return [
        [-2.60963981e-11, -2.59446215e-11, -2.58921890e-11, -2.59920566e-11,
         -2.59462214e-11, -2.59130079e-11, -2.60729916e-11, -2.60881712e-11,
         -2.59450462e-11, -2.58839030e-11, -2.59042083e-11, -2.58106121e-11,
         -2.59520187e-11, -2.59794448e-11, -2.60265342e-11, -2.58370900e-11,
         -2.59152893e-11, -2.58407936e-11, -2.57934473e-11, -2.59159609e-11,
         -2.59159412e-11, -2.58308878e-11, -2.59308739e-11, -2.59620331e-11,
         -2.59170275e-11, -2.58725454e-11, -2.59400192e-11, -2.60000859e-11,
         -2.59351700e-11, -2.59243359e-11, -2.60644586e-11, -2.59986045e-11],
        [-2.62161068e-11, -2.62253509e-11, -2.62674331e-11, -2.63032045e-11,
         -2.62306643e-11, -2.61316362e-11, -2.61618868e-11, -2.60880034e-11,
         -2.61383223e-11, -2.60528344e-11, -2.61278832e-11, -2.61204366e-11,
         -2.61638818e-11, -2.61737184e-11, -2.63791718e-11, -2.63065723e-11,
         -2.62892594e-11, -2.64172543e-11, -2.64786839e-11, -2.61944781e-11,
         -2.62018950e-11, -2.61602473e-11, -2.62598088e-11, -2.62039394e-11,
         -2.62713836e-11, -2.64028647e-11, -2.63589455e-11, -2.62574187e-11,
         -2.62998466e-11, -2.63225025e-11, -2.61002794e-11, -2.62119193e-11]
    ]


@pytest.fixture
def scan_last_vals():
    return [
       [-2.59144005e-11, -2.61250586e-11, -2.60600637e-11, -2.59626751e-11,
        -2.61486231e-11, -2.60371017e-11, -2.59465078e-11, -2.59519496e-11,
        -2.60158581e-11, -2.59390217e-11, -2.60349981e-11, -2.59730747e-11,
        -2.59557321e-11, -2.60830554e-11, -2.61766417e-11, -2.61883252e-11,
        -2.61872487e-11, -2.61141159e-11, -2.62214004e-11, -2.61541538e-11,
        -2.62246398e-11, -2.61697087e-11, -2.62161266e-11, -2.60474322e-11,
        -2.59854100e-11, -2.60087374e-11, -2.60266725e-11, -2.60474322e-11,
        -2.61595165e-11, -2.61731555e-11, -2.62116329e-11, -2.62146550e-11],
       [-2.62772797e-11, -2.61556253e-11, -2.59891234e-11, -2.60723694e-11,
        -2.62433057e-11, -2.60613180e-11, -2.60327463e-11, -2.60046882e-11,
        -2.60572589e-11, -2.60531998e-11, -2.60431755e-11, -2.60149791e-11,
        -2.59841359e-11, -2.60231763e-11, -2.60415657e-11, -2.59898937e-11,
        -2.60364894e-11, -2.59986539e-11, -2.59687983e-11, -2.58404479e-11,
        -2.59482460e-11, -2.61235180e-11, -2.59503299e-11, -2.59549816e-11,
        -2.58718442e-11, -2.60472544e-11, -2.60136557e-11, -2.59439993e-11,
        -2.59994637e-11, -2.58473908e-11, -2.59142523e-11, -2.60503752e-11]
    ]


def test_read_scan(scan_md_path, channels, units, scan_first_vals,
                   scan_last_vals):
    reader = reader_sxm.SXMScanReader(scan_md_path)
    datasets = reader.read()

    for idx, ds in enumerate(datasets):
        # Compare channels/units
        assert datasets[idx].quantity == channels[idx]
        assert datasets[idx].units == units[idx]

        # Compare first and last rows with what we expect
        expected_first = np.array(scan_first_vals[idx], dtype=float)
        expected_last = np.array(scan_last_vals[idx], dtype=float)
        assert np.allclose(datasets[idx].compute()[0, :], expected_first)
        assert np.allclose(datasets[idx].compute()[-1, :], expected_last)
