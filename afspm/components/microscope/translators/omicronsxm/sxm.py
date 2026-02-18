"""Main interface with SXM controller.

The code for this interface was modified from that provided by Omicron SXM.
We keep the copyright below; note that changes are shown in the git history.


 * (C) Copyright 02/2017
 *
 * Anfatec Instruments AG
 * Melanchthonstr. 28
 * 08606 Oelsnitz/i.V.
 * Germany
 * http://www.anfatec.de/
 *
 * Feel free to use it.
 *

Send DDE Execute command to running program

copyright recipe-577654-1
changed by Falk mailbox@anfatec.de
"""
import logging

from typing import Any, Callable
from ctypes import POINTER, WINFUNCTYPE, c_char_p, c_void_p, c_int, c_ulong
from ctypes.wintypes import BOOL, DWORD, LPCWSTR, UINT

import configparser


logger = logging.getLogger(__name__)


# DECLARE_HANDLE(name) typedef void *name;
HCONV = c_void_p  # = DECLARE_HANDLE(HCONV)
HDDEDATA = c_void_p  # = DECLARE_HANDLE(HDDEDATA)
HSZ = c_void_p  # = DECLARE_HANDLE(HSZ)
LPBYTE = c_char_p  # POINTER(BYTE)
LPDWORD = POINTER(DWORD)
LPSTR = c_char_p
ULONG_PTR = c_ulong

# See windows/ddeml.h for declaration of struct CONVCONTEXT
PCONVCONTEXT = c_void_p

DMLERR_NO_ERROR = 0

# Predefined Clipboard Formats
CF_TEXT = 1
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_SYLK = 4
CF_DIF = 5
CF_TIFF = 6
CF_OEMTEXT = 7
CF_DIB = 8
CF_PALETTE = 9
CF_PENDATA = 10
CF_RIFF = 11
CF_WAVE = 12
CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
CF_HDROP = 15
CF_LOCALE = 16
CF_DIBV5 = 17
CF_MAX = 18

DDE_FACK = 0x8000
DDE_FBUSY = 0x4000
DDE_FDEFERUPD = 0x4000
DDE_FACKREQ = 0x8000
DDE_FRELEASE = 0x2000
DDE_FREQUESTED = 0x1000
DDE_FAPPSTATUS = 0x00FF
DDE_FNOTPROCESSED = 0x0000

DDE_FACKRESERVED = (~(DDE_FACK | DDE_FBUSY | DDE_FAPPSTATUS))
DDE_FADVRESERVED = (~(DDE_FACKREQ | DDE_FDEFERUPD))
DDE_FDATRESERVED = (~(DDE_FACKREQ | DDE_FRELEASE | DDE_FREQUESTED))
DDE_FPOKRESERVED = (~(DDE_FRELEASE))

XTYPF_NOBLOCK = 0x0002
XTYPF_NODATA = 0x0004
XTYPF_ACKREQ = 0x0008

XCLASS_MASK = 0xFC00
XCLASS_BOOL = 0x1000
XCLASS_DATA = 0x2000
XCLASS_FLAGS = 0x4000
XCLASS_NOTIFICATION = 0x8000

XTYP_ERROR = (0x0000 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK)
XTYP_ADVDATA = (0x0010 | XCLASS_FLAGS)
XTYP_ADVREQ = (0x0020 | XCLASS_DATA | XTYPF_NOBLOCK)
XTYP_ADVSTART = (0x0030 | XCLASS_BOOL)
XTYP_ADVSTOP = (0x0040 | XCLASS_NOTIFICATION)
XTYP_EXECUTE = (0x0050 | XCLASS_FLAGS)
XTYP_CONNECT = (0x0060 | XCLASS_BOOL | XTYPF_NOBLOCK)
XTYP_CONNECT_CONFIRM = (0x0070 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK)
XTYP_XACT_COMPLETE = (0x0080 | XCLASS_NOTIFICATION )
XTYP_POKE = (0x0090 | XCLASS_FLAGS)
XTYP_REGISTER = (0x00A0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK )
XTYP_REQUEST = (0x00B0 | XCLASS_DATA )
XTYP_DISCONNECT = (0x00C0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK )
XTYP_UNREGISTER = (0x00D0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK )
XTYP_WILDCONNECT = (0x00E0 | XCLASS_DATA | XTYPF_NOBLOCK)
XTYP_MONITOR = (0x00F0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK)

XTYP_MASK = 0x00F0
XTYP_SHIFT = 4

TIMEOUT_ASYNC = 0xFFFFFFFF


def get_winfunc(libname, funcname, restype=None, argtypes=(), _libcache={}):
    """Retrieve a function from a library, and set the data types."""
    from ctypes import windll

    if libname not in _libcache:
        _libcache[libname] = windll.LoadLibrary(libname)
    func = getattr(_libcache[libname], funcname)
    func.argtypes = argtypes
    func.restype = restype

    return func


DDECALLBACK = WINFUNCTYPE(HDDEDATA, UINT, UINT, HCONV, HSZ, HSZ, HDDEDATA, 
                          ULONG_PTR, ULONG_PTR)


class DDE(object):
    """Object containing all the DDE functions."""

    AccessData = get_winfunc("user32", "DdeAccessData", LPBYTE,
                             (HDDEDATA, LPDWORD))
    ClientTransaction = get_winfunc("user32", "DdeClientTransaction", HDDEDATA,
                                    (LPBYTE, DWORD, HCONV, HSZ, UINT, UINT,
                                     DWORD, LPDWORD))
    Connect = get_winfunc("user32", "DdeConnect", HCONV,
                          (DWORD, HSZ, HSZ, PCONVCONTEXT))
    CreateStringHandle = get_winfunc("user32", "DdeCreateStringHandleW", HSZ,
                                     (DWORD, LPCWSTR, UINT))
    Disconnect = get_winfunc("user32", "DdeDisconnect", BOOL, (HCONV,))
    GetLastError = get_winfunc("user32", "DdeGetLastError", UINT, (DWORD,))
    Initialize = get_winfunc("user32", "DdeInitializeW", UINT,
                             (LPDWORD, DDECALLBACK, DWORD, DWORD))
    FreeDataHandle = get_winfunc("user32", "DdeFreeDataHandle", BOOL,
                                 (HDDEDATA,))
    FreeStringHandle = get_winfunc("user32", "DdeFreeStringHandle", BOOL,
                                   (DWORD, HSZ))
    QueryString = get_winfunc("user32", "DdeQueryStringA", DWORD,
                              (DWORD, HSZ, LPSTR, DWORD, c_int))
    UnaccessData = get_winfunc("user32", "DdeUnaccessData", BOOL, (HDDEDATA,))
    Uninitialize = get_winfunc("user32", "DdeUninitialize", BOOL, (DWORD,))


class DDEError(RuntimeError):
    """Exception raise when a DDE errpr occures."""

    def __init__(self, msg, idInst=None):
        """Init our error."""
        if idInst is None:
            RuntimeError.__init__(self, msg)
        else:
            RuntimeError.__init__(self, "%s (err=%s)" %
                                  (msg, hex(DDE.GetLastError(idInst))))


class DDEClient(object):
    """The DDEClient class.

    Use this class to create and manage a connection to a service/topic.
    To get classbacks subclass DDEClient and overwrite callback.
    """

    def __init__(self, service, topic):
        """Create a connection to a service/topic."""
        from ctypes import byref

        self._idInst = DWORD(0)
        self._hConv = HCONV()

        self._callback = DDECALLBACK(self._callback)
        res = DDE.Initialize(byref(self._idInst), self._callback, 0x00000010,
                             0)
        if res != DMLERR_NO_ERROR:
            raise DDEError("Unable to register with DDEML (err=%s)" % hex(res))

        hszService = DDE.CreateStringHandle(self._idInst, service, 1200)
        hszTopic = DDE.CreateStringHandle(self._idInst, topic, 1200)
        self._hConv = DDE.Connect(self._idInst, hszService, hszTopic,
                                  PCONVCONTEXT())
        DDE.FreeStringHandle(self._idInst, hszTopic)
        DDE.FreeStringHandle(self._idInst, hszService)
        if not self._hConv:
            raise DDEError("Unable to establish a conversation with server",
                           self._idInst)

        self.advise("Scan")
        self.advise('Command')
        self.advise('SaveFileName')
        self.advise('ScanLine')
        self.advise('MicState')
        self.advise('SpectSave')

        self.config = configparser.ConfigParser(strict=False)
        self.NotGotAnswer = False
        self.LastAnswer = ""

        self._scan_end_callback = None
        self._spect_save_callback = None

    def __del__(self):
        """Cleanup any active connections."""
        if self._hConv:
            DDE.Disconnect(self._hConv)
        if self._idInst:
            DDE.Uninitialize(self._idInst)

    def advise(self, item, stop=False):
        """Request updates when DDE data changes."""
        hszItem = DDE.CreateStringHandle(self._idInst, item, 1200)
        hDdeData = DDE.ClientTransaction(LPBYTE(), 0, self._hConv, hszItem,
                                         CF_TEXT, XTYP_ADVSTOP if stop
                                         else XTYP_ADVSTART, TIMEOUT_ASYNC,
                                         LPDWORD())
        DDE.FreeStringHandle(self._idInst, hszItem)
        if not hDdeData:
            raise DDEError("Unable to %s advise" % ("stop" if stop
                                                    else "start"),
                           self._idInst)
        DDE.FreeDataHandle(hDdeData)

    def execute(self, command, timeout=5000):
        """Execute a DDE command."""
        logger.trace(f'Executing: {command}')
        self.NotGotAnswer = True
        command = 'begin\r\n  '+command+'\r\nend.\r\n'
        command = bytes(command, 'utf-16')
        command = command.strip(b"\xff")
        command = command.strip(b"\xfe")
        pData = c_char_p(command)
        cbData = DWORD(len(command) + 1)
        # need utf-16 and fmt is ignored? Nov. 16 why?
        hDdeData = DDE.ClientTransaction(pData, cbData, self._hConv, HSZ(),
                                         CF_TEXT, XTYP_EXECUTE, timeout,
                                         LPDWORD())
        if not hDdeData:
            raise DDEError("Unable to send command", self._idInst)
        DDE.FreeDataHandle(hDdeData)

    def request(self, item, timeout=5000):
        """Request data from DDE service."""
        from ctypes import byref

        hszItem = DDE.CreateStringHandle(self._idInst, item, 1200)
        hDdeData = DDE.ClientTransaction(LPBYTE(), 0, self._hConv, hszItem,
                                         CF_TEXT, XTYP_REQUEST, timeout,
                                         LPDWORD())
        DDE.FreeStringHandle(self._idInst, hszItem)
        if not hDdeData:
            raise DDEError("Unable to request item", self._idInst)

        if timeout != TIMEOUT_ASYNC:
            pdwSize = DWORD(0)
            pData = DDE.AccessData(hDdeData, byref(pdwSize))
            if not pData:
                DDE.FreeDataHandle(hDdeData)
                raise DDEError("Unable to access data", self._idInst)
            # TODO: use pdwSize
            DDE.UnaccessData(hDdeData)
        else:
            pData = None
        DDE.FreeDataHandle(hDdeData)
        return pData

    def callback(self, value, item=None):
        """Handle responses to our requests."""
        if (value.startswith(b'Scan on')):
            # Do nothing, we do not appear to hit this.
            return
        elif (value.startswith(b'Scan off')):
            self.ScanOffCallback()
            return
        elif (item.startswith(b'SaveFileName')):
            # Do nothing, we determine scanning ends from ScanOffCallback
            return
        elif (item.startswith(b'ScanLine')):
            # Do nothing, we don't currently care when ScanLines are sent.
            return
        elif (item.startswith(b'MicState')):
            # Do nothing, we don't currently care when the 'mic state' changes.
            return
        elif (item.startswith(b'SpectSave')):
            self.SpectSave(value)
            return
        elif (item.startswith(b'Command')):
            self.LastAnswer = value
            self.NotGotAnswer = False
            return

        else:
            logger.error("Unknown callback %s: %s" % (item, value))  # TODO: Should this throw an exception?

    def _callback(self, wType, uFmt, hConv, hsz1, hsz2, hDdeData, dwData1,
                  dwData2):
        if wType == XTYP_XACT_COMPLETE:
            pass
        elif wType == XTYP_DISCONNECT:
            logger.info('Disconnect')
        elif wType == XTYP_ADVDATA:
            from ctypes import byref, create_string_buffer

            dwSize = DWORD(0)
            pData = DDE.AccessData(hDdeData, byref(dwSize))
            if pData:
                item = create_string_buffer(128)
                DDE.QueryString(self._idInst, hsz2, item, 128, 1004)
                self.callback(pData, item.value)
                DDE.UnaccessData(hDdeData)
            return DDE_FACK
        else:
            logger.info('Unhandled Callback' + hex(wType))

        return 0

    def on_scan_end_callback(self):
        """Once the scan ends, trigger callback."""
        if self._scan_end_callback:
            self._scan_end_callback()

    def on_spect_save(self, Value):
        """Once the spectroscopy ends, trigger callback."""
        if self._spect_save_callback:
            self._spect_save_callback()

    def get_ini_entry(self, section, item):
        """Get current iniFile."""
        IniName = self.request('IniFileName')
        IniName = str(IniName, 'utf-8')
        IniName = IniName.strip('\r\n')
        self.config.read(IniName)
        val = self.config.get(section, item)
        return val

    def execute_and_return(self, cmd) -> Any | None:
        """Execute a command that returns a val.

        The way this is implemented is that the command also prints
        whatever variable it got. The backend here reads what is printed
        as a response.
        """
        logger.trace(f'Executing: {cmd}')
        self.execute(cmd, 1000)

        while self.NotGotAnswer:
            loop()

        BackStr = self.LastAnswer
        BackStr = str(BackStr, 'utf-8').split('\r\n')
        logger.trace(f'Received answer: {BackStr}')
        if len(BackStr) >= 2:
            NrStr = BackStr[1].replace(',', '.')
            val = float(NrStr)
            return val
        return

    def register_spect_save_callback(self, callback: Callable):
        """Add a callable for when a spectroscopy is saved."""
        self._spect_save_callback = callback

    def register_scan_end_callback(self, callback: Callable):
        """Add a callable for when a scan ends."""
        self._scan_end_callback = callback


def loop():
    """Loop for reading from the interface."""
    from ctypes import POINTER, byref, c_ulong
    from ctypes.wintypes import BOOL, HWND, MSG, UINT

    LPMSG = POINTER(MSG)
    LRESULT = c_ulong
    GetMessage = get_winfunc("user32", "GetMessageW", BOOL, (LPMSG, HWND, UINT,
                                                             UINT))
    TranslateMessage = get_winfunc("user32", "TranslateMessage", BOOL,
                                   (LPMSG,))
    DispatchMessage = get_winfunc("user32", "DispatchMessageW", LRESULT,
                                  (LPMSG,))

    msg = MSG()
    lpmsg = byref(msg)
    GetMessage(lpmsg, HWND(), 0, 0)
    TranslateMessage(lpmsg)
    DispatchMessage(lpmsg)
