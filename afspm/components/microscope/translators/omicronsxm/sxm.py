'''
 * (C) Copyright 02/2017 /21
 *
 * Anfatec Instruments AG 
 * Melanchthonstr. 28 
 * 08606 Oelsnitz/i.V.
 * Germany
 * http://www.anfatec.de/
 *
 * Feel free to use it.
 *
 
'''

#!/usr/bin/env python
# Send DDE Execute command to running program

# copyright recipe-577654-1
# changed by Falk mailbox@anfatec.de

#import SXMRemote  # 25/01/2021
import ctypes
import threading
import time
# import win32event    # this function is used for 32 bit Python, only
from ctypes import POINTER, WINFUNCTYPE, c_char_p, c_void_p, c_int, c_ulong, c_char_p
from ctypes.wintypes import BOOL, DWORD, BYTE, INT, LPCWSTR, UINT, ULONG

import configparser

# DECLARE_HANDLE(name) typedef void *name;
HCONV     = c_void_p  # = DECLARE_HANDLE(HCONV)
HDDEDATA  = c_void_p  # = DECLARE_HANDLE(HDDEDATA)
HSZ       = c_void_p  # = DECLARE_HANDLE(HSZ)
LPBYTE    = c_char_p  # POINTER(BYTE)
LPDWORD   = POINTER(DWORD)
LPSTR    = c_char_p
ULONG_PTR = c_ulong

# See windows/ddeml.h for declaration of struct CONVCONTEXT
PCONVCONTEXT = c_void_p

DMLERR_NO_ERROR = 0

# Predefined Clipboard Formats
CF_TEXT         =  1
CF_BITMAP       =  2
CF_METAFILEPICT =  3
CF_SYLK         =  4
CF_DIF          =  5
CF_TIFF         =  6
CF_OEMTEXT      =  7
CF_DIB          =  8
CF_PALETTE      =  9
CF_PENDATA      = 10
CF_RIFF         = 11
CF_WAVE         = 12
CF_UNICODETEXT  = 13
CF_ENHMETAFILE  = 14
CF_HDROP        = 15
CF_LOCALE       = 16
CF_DIBV5        = 17
CF_MAX          = 18

DDE_FACK          = 0x8000
DDE_FBUSY         = 0x4000
DDE_FDEFERUPD     = 0x4000
DDE_FACKREQ       = 0x8000
DDE_FRELEASE      = 0x2000
DDE_FREQUESTED    = 0x1000
DDE_FAPPSTATUS    = 0x00FF
DDE_FNOTPROCESSED = 0x0000

DDE_FACKRESERVED  = (~(DDE_FACK | DDE_FBUSY | DDE_FAPPSTATUS))
DDE_FADVRESERVED  = (~(DDE_FACKREQ | DDE_FDEFERUPD))
DDE_FDATRESERVED  = (~(DDE_FACKREQ | DDE_FRELEASE | DDE_FREQUESTED))
DDE_FPOKRESERVED  = (~(DDE_FRELEASE))

XTYPF_NOBLOCK        = 0x0002
XTYPF_NODATA         = 0x0004
XTYPF_ACKREQ         = 0x0008

XCLASS_MASK          = 0xFC00
XCLASS_BOOL          = 0x1000
XCLASS_DATA          = 0x2000
XCLASS_FLAGS         = 0x4000
XCLASS_NOTIFICATION  = 0x8000

XTYP_ERROR           = (0x0000 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK)
XTYP_ADVDATA         = (0x0010 | XCLASS_FLAGS)
XTYP_ADVREQ          = (0x0020 | XCLASS_DATA | XTYPF_NOBLOCK)
XTYP_ADVSTART        = (0x0030 | XCLASS_BOOL)
XTYP_ADVSTOP         = (0x0040 | XCLASS_NOTIFICATION)
XTYP_EXECUTE         = (0x0050 | XCLASS_FLAGS)
XTYP_CONNECT         = (0x0060 | XCLASS_BOOL | XTYPF_NOBLOCK)
XTYP_CONNECT_CONFIRM = (0x0070 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK)
XTYP_XACT_COMPLETE   = (0x0080 | XCLASS_NOTIFICATION )
XTYP_POKE            = (0x0090 | XCLASS_FLAGS)
XTYP_REGISTER        = (0x00A0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK )
XTYP_REQUEST         = (0x00B0 | XCLASS_DATA )
XTYP_DISCONNECT      = (0x00C0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK )
XTYP_UNREGISTER      = (0x00D0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK )
XTYP_WILDCONNECT     = (0x00E0 | XCLASS_DATA | XTYPF_NOBLOCK)
XTYP_MONITOR         = (0x00F0 | XCLASS_NOTIFICATION | XTYPF_NOBLOCK)

XTYP_MASK            = 0x00F0
XTYP_SHIFT           = 4

TIMEOUT_ASYNC        = 0xFFFFFFFF

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
    """Object containing all the DDE functions"""
    AccessData         = get_winfunc("user32", "DdeAccessData",          LPBYTE,   (HDDEDATA, LPDWORD))
    ClientTransaction  = get_winfunc("user32", "DdeClientTransaction",   HDDEDATA, (LPBYTE, DWORD, HCONV, HSZ, UINT, UINT, DWORD, LPDWORD))
    Connect            = get_winfunc("user32", "DdeConnect",             HCONV,    (DWORD, HSZ, HSZ, PCONVCONTEXT))
    CreateStringHandle = get_winfunc("user32", "DdeCreateStringHandleW", HSZ,      (DWORD, LPCWSTR, UINT))
    Disconnect         = get_winfunc("user32", "DdeDisconnect",          BOOL,     (HCONV,))
    GetLastError       = get_winfunc("user32", "DdeGetLastError",        UINT,     (DWORD,))
    Initialize         = get_winfunc("user32", "DdeInitializeW",         UINT,     (LPDWORD, DDECALLBACK, DWORD, DWORD))
    FreeDataHandle     = get_winfunc("user32", "DdeFreeDataHandle",      BOOL,     (HDDEDATA,))
    FreeStringHandle   = get_winfunc("user32", "DdeFreeStringHandle",    BOOL,     (DWORD, HSZ))
    QueryString        = get_winfunc("user32", "DdeQueryStringA",        DWORD,    (DWORD, HSZ, LPSTR, DWORD, c_int))
    UnaccessData       = get_winfunc("user32", "DdeUnaccessData",        BOOL,     (HDDEDATA,))
    Uninitialize       = get_winfunc("user32", "DdeUninitialize",        BOOL,     (DWORD,))

class DDEError(RuntimeError):
    """Exception raise when a DDE errpr occures."""
    def __init__(self, msg, idInst=None):
        if idInst is None:
            RuntimeError.__init__(self, msg)
        else:
            RuntimeError.__init__(self, "%s (err=%s)" % (msg, hex(DDE.GetLastError(idInst))))

class DDEClient(object): #'self.' in whole class 
    """The DDEClient class.

    Use this class to create and manage a connection to a service/topic.  To get
    classbacks subclass DDEClient and overwrite callback."""

    def __init__(self, service, topic):
        """Create a connection to a service/topic."""
        from ctypes import byref

        self._idInst = DWORD(0)
        self._hConv = HCONV()

        self._callback = DDECALLBACK(self._callback)
        res = DDE.Initialize(byref(self._idInst), self._callback, 0x00000010, 0)
        if res != DMLERR_NO_ERROR:
            raise DDEError("Unable to register with DDEML (err=%s)" % hex(res))

        hszService = DDE.CreateStringHandle(self._idInst, service, 1200)
        hszTopic = DDE.CreateStringHandle(self._idInst, topic, 1200)
        self._hConv = DDE.Connect(self._idInst, hszService, hszTopic, PCONVCONTEXT())
        DDE.FreeStringHandle(self._idInst, hszTopic)
        DDE.FreeStringHandle(self._idInst, hszService)
        if not self._hConv:
            raise DDEError("Unable to establish a conversation with server", self._idInst)

        self.advise('Scan');
        self.advise('Command');
        self.advise('SaveFileName');
        self.advise('ScanLine');
        self.advise('MicState');
        self.advise('SpectSave');
        
        self.config=configparser.ConfigParser() #instantiate
        self.NotGotAnswer = False;
        self.LastAnswer = "";

        
    def __del__(self):
        """Cleanup any active connections."""
        if self._hConv:
            DDE.Disconnect(self._hConv)
        if self._idInst:
            DDE.Uninitialize(self._idInst)

    def advise(self, item, stop=False):
        """Request updates when DDE data changes."""
        from ctypes import byref
        hszItem = DDE.CreateStringHandle(self._idInst, item, 1200)
        hDdeData = DDE.ClientTransaction(LPBYTE(), 0, self._hConv, hszItem, CF_TEXT, XTYP_ADVSTOP if stop else XTYP_ADVSTART, TIMEOUT_ASYNC, LPDWORD())
        DDE.FreeStringHandle(self._idInst, hszItem)
        if not hDdeData:
            raise DDEError("Unable to %s advise" % ("stop" if stop else "start"), self._idInst)
        DDE.FreeDataHandle(hDdeData)

    def execute(self, command, timeout=5000):
        """Execute a DDE command."""
        self.NotGotAnswer=True
        # Dec. 16 we need utf16 without heater!
        command='begin\r\n  '+command+'\r\nend.\r\n';  #create pascal style program
        #print(command)
        command=bytes(command, 'utf-16');     #falk
        command=command.strip(b"\xff")        #falk
        command=command.strip(b"\xfe")        #falk
        pData = c_char_p(command)
        cbData = DWORD(len(command) + 1)
        #hDdeData = DDE.ClientTransaction(pData, cbData, self._hConv, HSZ(), CF_UNICODETEXT, XTYP_EXECUTE, timeout, LPDWORD())
        # need utf-16 and fmt is ignored? Nov. 16 why?		
        hDdeData = DDE.ClientTransaction(pData, cbData, self._hConv, HSZ(), CF_TEXT, XTYP_EXECUTE, timeout, LPDWORD())
        if not hDdeData:
            raise DDEError("Unable to send command", self._idInst)
        DDE.FreeDataHandle(hDdeData)

    def request(self, item, timeout=5000):
        """Request data from DDE service."""
        from ctypes import byref

        hszItem = DDE.CreateStringHandle(self._idInst, item, 1200)
        hDdeData = DDE.ClientTransaction(LPBYTE(), 0, self._hConv, hszItem, CF_TEXT, XTYP_REQUEST, timeout, LPDWORD())
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
        """Callback function for advice."""
        #print ("callback %s: %s" % (item, value))

        #value = str(value, 'utf-8') #Feb. 17
        #value = value.strip('\r\n') #Feb. 17

        self.LastAnswer = value;
        if (value.startswith(b'Scan on')):
            self.LastAnswer = 1
            self.ScanOnCallBack();     # print('on')
            return
        elif (value.startswith(b'Scan off')):
            self.LastAnswer = 0
            self.ScanOffCallBack();     # print('off')
            return
        elif (item.startswith(b'SaveFileName')):
            FileName=str(value,'utf-8').strip('\r\n')
            self.SaveIsDone(FileName);  # print('SaveIsDone')
            return
        elif (item.startswith(b'ScanLine')):
            value = str(value, 'utf-8').strip('\r\n')
            self.Scan(value);           # print('ScanLine')
            return
        elif (item.startswith(b'MicState')):
            self.MicState(value);
            return
        elif (item.startswith(b'SpectSave')):
            self.SpectSave(value);
            return
        elif (item.startswith(b'Command')): # echo of command
            self.LastAnswer = value;
            return
    
        else:
            print ("Unknown callback %s: %s" % (item, value))
        
    
    def _callback(self, wType, uFmt, hConv, hsz1, hsz2, hDdeData, dwData1, dwData2):
        if wType == XTYP_XACT_COMPLETE:
            pass #print('XTYP_XACT_COMPLETE');
        elif wType == XTYP_DISCONNECT:
            print('disconnect');
        elif wType == XTYP_ADVDATA:
            from ctypes import byref, create_string_buffer

            dwSize = DWORD(0)
            pData = DDE.AccessData(hDdeData, byref(dwSize))
            if pData:
                #falk item = create_string_buffer( '\000' * 128)
                item = create_string_buffer(128)
                DDE.QueryString(self._idInst, hsz2, item, 128, 1004)
                self.callback(pData, item.value)
                self.NotGotAnswer = False;
                DDE.UnaccessData(hDdeData)
                #print("set false");
            return DDE_FACK
        else:
            print('callback'+hex(wType));

        return 0
        
    def ScanOnCallBack (self):
        print('scan is on');

    def ScanOffCallBack (self) :
        print('scan is off');
    
    def SaveIsDone (self, FileName) :
        print(FileName);
        
    def Scan (self, LineNr) :
        pass  #print(LineNr); # 1st letter is u/d/f/b for up/down/forward/backward

    def MicState (self, Value) :
        print ('MicState '+ str(Value))

    def SpectSave (self, Value) :
        print ('SpectSave '+ str(Value))
        #print (str(Value))
    
    def StartMsgLoop (self):
        MsgLoop = MyMsgClass()
        MsgLoop.start()

    def GetIniEntry (self, section, item):
        #get current iniFile
        IniName=self.request('IniFileName');
        IniName=str(IniName,'utf-8')
        IniName=IniName.strip('\r\n')
        #config=configparser.ConfigParser() #instantiate
        self.config.read(IniName)
        val=self.config.get(section, item)
        return val

    def GetChannel (self, ch):
        string="a:=GetChannel("+str(ch)+");\r\n  writeln(a);"
        self.execute(string, 1000);

        while self.NotGotAnswer:
            loop();

        BackStr=self.LastAnswer;
        BackStr=str(BackStr,'utf-8').split('\r\n')
        print(BackStr)
        
        if len(BackStr)>=2:
            NrStr=BackStr[1].replace(',','.')
            val=float(NrStr)
            return val
        return

    def SendWait(self, command):
        self.execute(command, 1000);
        while self.NotGotAnswer:
            loop();


    def GetPara (self, TopicItem):
        self.execute(TopicItem,5000);

        while self.NotGotAnswer:
            loop();

        BackStr=self.LastAnswer;
        BackStr=str(BackStr,'utf-8').split('\r\n')
        if len(BackStr)>=2:
            NrStr=BackStr[1].replace(',','.')
            #print(NrStr)
            val=float(NrStr)
            return val
        return
  
    def GetScanPara (self, item):
        TopicItem="a:=GetScanPara('"+item+"');\r\n  writeln(a);"
        return self.GetPara(TopicItem)

    def GetFeedbackPara (self, item):
        TopicItem="a:=GetFeedPara('"+item+"');\r\n  writeln(a);"
        return self.GetPara(TopicItem)



class MyMsgClass (threading.Thread):
    """
        A threading
    """
    def __init__ (self):
        threading.Thread.__init__(self)
    def run(self):
        """Run the main windows message loop."""
        from ctypes import POINTER, byref, c_ulong
        from ctypes.wintypes import BOOL, HWND, MSG, UINT

        LPMSG = POINTER(MSG)
        LRESULT = c_ulong
        GetMessage = get_winfunc("user32", "GetMessageW", BOOL, (LPMSG, HWND, UINT, UINT))
        TranslateMessage = get_winfunc("user32", "TranslateMessage", BOOL, (LPMSG,))
        # restype = LRESULT
        DispatchMessage = get_winfunc("user32", "DispatchMessageW", LRESULT, (LPMSG,))

        msg = MSG()
        lpmsg = byref(msg)
        print ("Debug: Start Msg loop")
        while GetMessage(lpmsg, HWND(), 0, 0) > 0:
            TranslateMessage(lpmsg)
            DispatchMessage(lpmsg)
            print ("loop")

def loop():
    from ctypes import POINTER, byref, c_ulong
    from ctypes.wintypes import BOOL, HWND, MSG, UINT

    LPMSG = POINTER(MSG)
    LRESULT = c_ulong
    GetMessage = get_winfunc("user32", "GetMessageW", BOOL, (LPMSG, HWND, UINT, UINT))
    TranslateMessage = get_winfunc("user32", "TranslateMessage", BOOL, (LPMSG,))
    # restype = LRESULT
    DispatchMessage = get_winfunc("user32", "DispatchMessageW", LRESULT, (LPMSG,))

    msg = MSG()
    lpmsg = byref(msg)
    #print ("Start Msg loop")
    GetMessage(lpmsg, HWND(), 0, 0)
    TranslateMessage(lpmsg)
    DispatchMessage(lpmsg)
    #print ("end loop")


# Do not execute here. Otherwise the class will be instantiated twice
# and functins will run twice (25/01/21)
#MySXM = SXMRemote.DDEClient("SXM","Remote");
 

"""
if __name__ == "__main__":
    # Create a connection to ESOTS (OTS Swardfish) and to instrument MAR11 ALSI
    dde = DDEClient("ESOTS", "MAR11 ALSI")

    # Monitor the various attributes from MAR11 ALSI
    dde.advise("BIDQ")    # Last bid quantity
    dde.advise("BIDP")    # Last bid price
    dde.advise("ASKP")    # Last ask price
    dde.advise("ASKQ")    # Last ask quantity
    dde.advise("LASTP")   # Last traded price
    dde.advise("TIME")    # Last traded time
    dde.advise("VOL")     # Daily volume

    # Run the main message loop to receive advices
    WinMSGLoop()
"""


"""
    self.hWaitCommand=win32event.CreateEvent(None, 0,0, None);
    win32event.SetEvent(self.hWaitCommand)
    #win32event.ResetEvent(self.hWaitCommand)
    #res=win32event.WaitForSingleObject(self.hWaitCommand, 10000)

"""
