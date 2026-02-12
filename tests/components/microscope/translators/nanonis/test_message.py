"""Test Nanonis message packing/unpacking."""

import pytest
import logging
import struct
from afspm.components.microscope.translators.nanonis.message import base, probe


logger = logging.getLogger(__name__)


@pytest.fixture
def command_name():  # FolMe.XYPosGet
    return struct.pack('32s', 'FolMe.XYPosGet'.encode('utf-8'))


@pytest.fixture
def req_body_size():  # 4 bytes
    return bytearray.fromhex('0000 0004')


@pytest.fixture
def send_response_back():  # True
    return bytearray.fromhex('0001')


@pytest.fixture
def req_not_used():  # 2 bytes of 0's
    return bytearray.fromhex('0000')


@pytest.fixture
def wait_for_newest_data():  # True
    return bytearray.fromhex('0000 0001')


@pytest.fixture
def expected_request(command_name, req_body_size, send_response_back,
                     req_not_used, wait_for_newest_data):
    return (command_name + req_body_size + send_response_back +
            req_not_used + wait_for_newest_data)


def test_to_bytes(expected_request):
    logger.info('Validate we can properly create a request and convert to'
                ' bytes.')

    req = probe.XYPosGetReq(wait_for_newest_data=1)  # i.e. True
    req_bytes = base.to_bytes(req)

    assert req_bytes == expected_request


@pytest.fixture
def rep_body_size():  # 24 bytes
    return bytearray.fromhex('0000 0018')


@pytest.fixture
def rep_not_used():  # 4 bytes of 0's
    return bytearray.fromhex('0000 0000')


@pytest.fixture
def x_m():  # 5 nm
    return bytearray.fromhex('3E35 798E E230 8C3A')


@pytest.fixture
def y_m():  # -5 nm
    return bytearray.fromhex('BE35 798E E230 8C3A')


@pytest.fixture
def error_status():  # False
    return bytearray.fromhex('0000 0000')


@pytest.fixture
def error_description_size():  # 0
    return bytearray.fromhex('0000 0000')


@pytest.fixture
def error_description():
    return bytearray.fromhex('')


@pytest.fixture
def response_bytes(command_name, rep_body_size, rep_not_used, x_m, y_m,
                   error_status, error_description_size, error_description):
    return (command_name + rep_body_size + rep_not_used + x_m + y_m +
            error_status + error_description_size + error_description)


@pytest.fixture
def expected_rep():
    rep = probe.XYPosGetRep(x=5e-9, y=-5e-9)
    return rep


def test_from_bytes(response_bytes, expected_rep):
    logger.info('Validate we can properly convert a received response'
                ' in bytes format to its associated NanonisResponse.')

    rep = probe.XYPosGetRep(x=0, y=0)  # TODO Change if you setup defaults
    rep = base.from_bytes(response_bytes, rep)

    assert rep == expected_rep
