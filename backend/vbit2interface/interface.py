import socket
import warnings
import time
from enum import Enum, IntEnum
from collections import namedtuple

class __Command__(Enum):
    ''' VBIT2 interface command byte sequence magic numbers.
    '''
    SETCHAN     = b'\x00'
    DCRAW       = b'\x01\x00'
    DCFORMATA   = b'\x01\x01'
    DCFORMATB   = b'\x01\x02'
    CONFRAFLAG  = b'\x02\x00'
    CONFRBYTES  = b'\x02\x01'
    CONFSTATUS  = b'\x02\x02'
    CONFHEADER  = b'\x02\x03'
    CONFENHANC  = b'\x02\x04'
    PAGEDELETE  = b'\x03\x00'
    PAGEOPEN    = b'\x03\x01'
    PAGESETSUB  = b'\x03\x02'
    PAGEDELSUB  = b'\x03\x03'
    PAGECLOSE   = b'\x03\x04'
    PAGEFANDC   = b'\x03\x05'
    PAGEOPTNS   = b'\x03\x06'
    PAGEROW     = b'\x03\x07'
    PAGELINKS   = b'\x03\x08'
    GETAPIVER   = b'\x04'
    
    def __get__(self, instance, owner):
        return self.value

class __Error__(IntEnum):
    ''' VBIT2 interface error/status code values.
    '''
    CMDOK    = 0x00,
    CMDTRUNC = 0xFC,
    CMDNOENT = 0xFD,
    CMDBUSY  = 0xFE,
    CMDERR   = 0xFF

class ResourceBusyError(RuntimeError):
    ''' Interface server temporarily unable to complete command.
    '''
    def __init__(self, msg):
        self.msg = msg

class VersionError(RuntimeError):
    ''' Command not compatible with version number reported by server.
    '''
    def __init__(self, msg):
        self.msg = msg

class Client:
    ''' VBIT2 interface client
    
    :param host: Hostname of server.
    :param port: Port number of server.
    '''
    __APIVER = (1,1,0) # what API version this module implements
    
    def __init__(self, host, port):
        self.__host = host
        self.__port = port
        self.__sock = None
        self.DEFAULT_RETRIES = 5 # Number of retries
        self.DEFAULT_INTERVAL = 4 # Retry interval - four fields
        self.connect()
    
    def connect(self):
        '''Attempt to connect to VBIT2 control interface server and interrogate API version.
        
        :raise VersionError: The server reports a future major version.
        '''
        self.close()
        try:
            self.__sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except OSError as msg:
            self.__sock = None
            raise
        self.__sock.connect((self.__host, self.__port))
        self.__version = self.getVersion()
    
    def close(self):
        '''Close network connection and clear state.
        '''
        if not self.__sock is None:
            self.__sock.close()
        self.__sock = None
        self.__version = (0,0,0)
        self.__chan = None
        self.__page = None
        self.__subpage = None
    
    def __send(self, message):
        b = bytearray([0])
        b.extend(message)
        b[0] = len(b)
        self.__sock.send(b)
        res = self.__sock.recv(1)
        res = self.__sock.recv(res[0])
        return res
    
    def getVersion(self):
        '''Interrogate API version of server.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error.
        :raise VersionError: The server reports a future major version.
        '''
        if not self.__sock is None:
            res = self.__send(__Command__.GETAPIVER)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            if res[1] > self.__APIVER[0]:
                # Server major version is greater than this module. There could be breaking changes
                raise VersionError('Incompatible server version')
            return namedtuple('APIVER', 'major minor patch')(res[1], res[2], res[3])
        else:
            raise ConnectionError
    
    def setChannel(self, channel):
        '''Select interface channel number on server.
        
        :param channel: channel number from 0 to 15.
        
        :raise ConnectionError: No connection to server.
        :raise ResourceBusyError: Channel is already in use.
        :raise RuntimeError: Server returned an unexpected error.
        :raise ValueError: Invalid channel argument.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            self.__chan = None
            if channel < 0 or channel > 15:
                raise ValueError('Channel must be in the range 0-15')
            if not self.__sock is None:
                res = self.__send(__Command__.SETCHAN + bytes([channel]))
                if res[0] == __Error__.CMDOK:
                    self.__chan = channel
                elif res[0] == __Error__.CMDBUSY:
                    raise ResourceBusyError('Channel busy')
                else:
                    raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def datacastRaw(self, data, retries=None):
        '''Inject 40 bytes of pre-encoded data into data broadcast buffer.
        
        Automatically retries command if server reports buffer is full.
        
        :param data: bytes or bytearray containing exactly 40 bytes.
        :param retries: optionally override the number of attempts.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid data length.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 40:
                 raise ValueError('Must be exactly 40 bytes')
            if self.__chan is None or self.__chan == 0:
                raise RuntimeError('Invalid channel')
            
            if retries is None:
                retries = self.DEFAULT_RETRIES
            while True:
                res = self.__send(__Command__.DCRAW + data)
                if res[0] == __Error__.CMDOK:
                    break
                elif res[0] == __Error__.CMDBUSY:
                    if retries == 0:
                        raise ResourceBusyError('Datacast buffer is full')
                        break
                    time.sleep(0.04) # delay one frame period
                    retries = retries-1
                else:
                    raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def datacastFormatA(self, data, IAL=0, SPA=0, CI=0, RI=None, explicitCI=False, useDL=False, retries=None):
        '''Create Format A data broadcast packet and insert into transmission buffer.
        
        Automatically retries command if server reports buffer is full.
        
        :return: Number of bytes successfully transmitted.
        
        :param data: bytes or bytearray containing payload.
        :param IAL: Interpretation and Address Length.
        :param SPA: Service Packet Address.
        :param CI: Continuity Indicator.
        :param RI: Repeat Indicator.
        :param explicitCI: flag to enable an explicit continuity indicator byte.
        :param useDL: flag to enable a Data Length byte.
        :param retries: optionally override the number of attempts.
        
        :raise ConnectionError: No connection to server.
        :raise ResourceBusyError: Data broadcast buffer is full.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid IAL argument.
        :raise VersionError: Server version is too old for this command.
        '''
        
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if IAL < 0 or IAL > 6:
                raise ValueError('IAL must be in the range 0-6')
            IAL = IAL << 4
            if RI is not None:
                IAL |= 2
            else:
                RI = 0
            if explicitCI is True:
                IAL |= 4
            if useDL is True:
                IAL |= 8
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if self.__chan is None or self.__chan == 0:
                raise RuntimeError('Invalid channel')
                
            if retries is None or retries < 0:
                retries = self.DEFAULT_RETRIES
            while True:
                res = self.__send(__Command__.DCFORMATA + bytearray([IAL, SPA&0xff, (SPA>>8)&0xff, (SPA>>16)&0xff, RI, CI]) + data)
                if res[0] == __Error__.CMDOK:
                    break
                elif res[0] == __Error__.CMDTRUNC:
                    break
                elif res[0] == __Error__.CMDBUSY:
                    if retries == 0:
                        raise ResourceBusyError('Datacast buffer is full')
                        break
                    time.sleep(0.04) # delay one frame period
                    retries = retries-1
                else:
                    raise RuntimeError('Server returned unexpected error')
            return res[1] # number of bytes transmitted
        else:
            raise ConnectionError
    
    def datacastFormatB(self, AN, AI, data, retries=None):
        '''Inject 490 byte Format B data broadcast bundle into buffer.
        
        Automatically retries command if server reports buffer is full.
        
        :param data: bytes or bytearray containing payload.
        :param AN: Databroadcast Application Number.
        :param AI: Databroadcast Application Identifier.
        :param retries: optionally override the number of attempts.
        
        :raise ConnectionError: No connection to server.
        :raise ResourceBusyError: Data broadcast buffer is full.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid AN or AI argument, or data bundle incorrect length.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 1, 0):
                raise VersionError('Command not supported by this server')
            if AN < 0 or AN > 3:
                raise ValueError('AN must be in the range 0-3')
            if AI < 0 or AI > 15:
                raise ValueError('AI must be in the range 0-15')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 490:
                 raise ValueError('Must be exactly 490 bytes')
            if self.__chan is None or self.__chan == 0:
                raise RuntimeError('Invalid channel')
            
            if retries is None:
                retries = self.DEFAULT_RETRIES
            while True:
                res = self.__send(__Command__.DCFORMATB + bytes([AN | (AI << 2)]) + data[0:245]) # send first half of data bundle
                if res[0] == __Error__.CMDOK:
                    res = self.__send(__Command__.DCFORMATB + bytes([AN | (AI << 2) | 0x80]) + data[245:490]) # second half of bundle
                    if res[0] != __Error__.CMDOK:
                        raise RuntimeError('Server returned unexpected error')
                    break
                elif res[0] == __Error__.CMDBUSY:
                    if retries == 0:
                        raise ResourceBusyError('Datacast buffer is full')
                        break
                    time.sleep(0.04) # delay one frame period
                    retries = retries-1
                else:
                    raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def getRowAdaptive(self):
        '''Read state of Row Adaptive transmission mode flag.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            res = self.__send(__Command__.CONFRAFLAG)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return res[1]==1
        else:
            raise ConnectionError
    def setRowAdaptive(self, flag):
        '''Set state of Row Adaptive transmission mode flag.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid flag.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if not type(flag) is bool:
                raise TypeError('Must be boolean')
            res = self.__send(__Command__.CONFRAFLAG + bytes([int(flag)]))
            if res[0] == __Error__.CMDERR:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def getBSDPReserved(self):
        '''Read reserved bytes of Broadcast Service Data Packet.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            res = self.__send(__Command__.CONFRBYTES)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return bytes(res[1:5])
        else:
            raise ConnectionError
    def setBSDPReserved(self, data):
        '''Set reserved bytes of Broadcast Service Data Packet.
        
        :param data: bytes or bytearray containing exactly 4 bytes.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid data length.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 4:
                raise ValueError('Must be exactly 4 bytes')
            res = self.__send(__Command__.CONFRBYTES + data)
            if res[0] == __Error__.CMDERR:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def getBSDPStatus(self):
        '''Read Broadcast Service Data Packet status display message.
        
        :return: 20 bytes of character data.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            res = self.__send(__Command__.CONFSTATUS)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return bytes(res[1:21])
        else:
            raise ConnectionError
    def setBSDPStatus(self, data):
        '''Set Broadcast Service Data Packet status display message.
        
        :param data: bytes or bytearray containing exactly 20 bytes.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid data length
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 20:
                raise ValueError('Must be exactly 20 bytes')
            res = self.__send(__Command__.CONFSTATUS + data)
            if res[0] == __Error__.CMDERR:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def getHeaderTemplate(self, magazine=None):
        '''Read VBIT2 header template.
        
        :return: 32 bytes of character data.
        
        :param magazine: optional magazine number in range 1 to 8 to read magazine specific template.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no header template set.
        :raise ValueError: Invalid magazine number.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if not magazine is None:
                if magazine < 1 or magazine > 8:
                    raise ValueError('Invalid magazine number')
                res = self.__send(__Command__.CONFHEADER + bytes([magazine&7]))
            else:
                res = self.__send(__Command__.CONFHEADER)
            if res[0] == __Error__.CMDNOENT:
                raise RuntimeError('No header template set')
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return bytes(res[1:33])
        else:
            raise ConnectionError
    def setHeaderTemplate(self, data, magazine=None):
        '''Set VBIT2 header template.
        
        :param data: bytes or bytearray containing exactly 32 bytes.
        :param magazine: optional magazine number in range 1 to 8 to set template for a single magazine.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid data length or magazine number.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 32:
                raise ValueError('Must be exactly 32 bytes')
            if not magazine is None:
                if magazine < 1 or magazine > 8:
                    raise ValueError('Invalid magazine number')
                res = self.__send(__Command__.CONFHEADER + bytes([magazine&7]) + data)
            else:
                res = self.__send(__Command__.CONFHEADER + data)
            if res[0] == __Error__.CMDERR:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    def clearHeaderTemplate(self, magazine):
        '''Clear magazine specific VBIT2 header template.
        
        :param magazine: magazine number in range 1 to 8.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise ValueError: Invalid magazine number.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if magazine < 1 or magazine > 8:
                raise ValueError('Invalid magazine number')
            res = self.__send(__Command__.CONFHEADER + bytes([0x80 | (magazine&7)]))
            if res[0] == __Error__.CMDERR:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def getMagEnhancement(self, magazine, designationCode):
        '''Read magazine enhancement packet.
        
        :return: 40 bytes of packet data using VBIT2 triplet encoding.
        
        :param magazine: magazine number in range 1 to 8.
        :param designationCode: packet designation code in range 0 to 15.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or packet does not exist.
        :raise ValueError: Invalid magazine number or designation code.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if magazine < 1 or magazine > 8:
                raise ValueError('Invalid magazine number')
            if designationCode < 0 or designationCode > 15:
                raise ValueError('Invalid designation code')
            else:
                res = self.__send(__Command__.CONFENHANC + bytes([magazine&7, designationCode]))
            if res[0] == __Error__.CMDNOENT:
                raise RuntimeError('Packet does not exist')
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return bytes(res[1:41])
        else:
            raise ConnectionError
    
    def setMagEnhancement(self, magazine, data):
        '''Set magazine enhancement packet.
        
        :param magazine: magazine number in range 1 to 8.
        :param data: bytes or bytearray containing exactly 40 bytes using VBIT2 triplet encoding.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid magazine number or data length.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if magazine < 1 or magazine > 8:
                raise ValueError('Invalid magazine number')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 40:
                 raise ValueError('Must be exactly 40 bytes')
            res = self.__send(__Command__.CONFENHANC + bytes([magazine&7]) + data)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def deleteMagEnhancement(self, magazine, designationCode=None):
        '''Delete magazine enhancement packet(s).
        
        :param magazine: magazine number in range 1 to 8.
        :param designationCode: optional packet designation code in range 0 to 15.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error or invalid channel.
        :raise ValueError: Invalid magazine number or designation code.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if magazine < 1 or magazine > 8:
                raise ValueError('Invalid magazine number')
            if designationCode is None:
                res = self.__send(__Command__.CONFENHANC + bytes([0x80 | (magazine&7)]))
            else:
                if designationCode < 0 or designationCode > 15:
                    raise ValueError('Invalid designation code')
                res = self.__send(__Command__.CONFENHANC + bytes([0x80 | (magazine&7), designationCode]))
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    
    def deletePage(self, number):
        '''Delete a page from the teletext service.
        
        :param number: hexadecimal page number.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, or invalid channel.
        :raise ValueError: Invalid page number.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if number < 0x100 or number > 0x8FF or number & 0xFF == 0xFF:
                raise ValueError('Invalid page number')
            res = self.__send(__Command__.PAGEDELETE + bytes([number >> 8, number & 0xff]))
            self.__page = None # sending this command closed any open page
            self.__subpage = None # which cleared any subpage
            if res[0] == __Error__.CMDNOENT:
                # don't raise an exception because the end result is the same
                msg = 'Page {0:X} not found in service'.format(number)
                warnings.warn(msg) 
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def openPage(self, number, oneShot=False, retries=None, interval=None):
        '''Open/create page in teletext service.
        
        :param number: hexadecimal page number.
        :param oneShot: flag to set page to one shot transmission.
        :param retries: optionally override the number of attempts.
        :param interval: optionally override retry interval.
        
        :raise ConnectionError: No connection to server.
        :raise ResourceBusyError: Page is currently locked.
        :raise RuntimeError: Server returned an unexpected error, or invalid channel.
        :raise TypeError: Invalid oneShot flag.
        :raise ValueError: Invalid page number.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if number < 0x100 or number > 0x8FF or number & 0xFF == 0xFF:
                raise ValueError('Invalid page number')
            if type(oneShot) is not bool:
                raise TypeError('oneShot flag must be boolean')
            self.__page = None # sending this command close any open page
            self.__subpage = None # which clears any subpage
            
            flags = oneShot is True
            
            if retries is None or retries < 0:
                retries = self.DEFAULT_RETRIES
            if interval is None or interval < 1:
                interval = self.DEFAULT_INTERVAL
            while True:
                res = self.__send(__Command__.PAGEOPEN + bytes([number >> 8, number & 0xff, flags]))
                if res[0] == __Error__.CMDOK:
                    break
                elif res[0] == __Error__.CMDBUSY:
                    if retries == 0:
                        raise ResourceBusyError('Page is currently locked')
                        break
                    time.sleep(0.02 * interval)
                    retries = retries-1
                else:
                    raise RuntimeError('Server returned unexpected error')
            self.__page = number # the page has been opened for us
        else:
            raise ConnectionError
    
    def setSubPage(self, subcode):
        '''Select/create sub-page in open page.
        
        :return: Number of sub pages in page.
        
        :param subcode: hexadecimal sub-code number.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no page open.
        :raise ValueError: Invalid subcode.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__page is None:
                raise RuntimeError('No page open')
            if subcode < 0 or subcode > 0x3F7E or subcode & 0xC080:
                raise ValueError('Invalid subcode')
            res = self.__send(__Command__.PAGESETSUB + bytes([subcode >> 8, subcode & 0xff]))
            self.__subpage = None # sending this command deselected any subpage
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            self.__subpage = subcode # the subpage has been selected
            return (res[1] << 8) | res[2] # return number of subpages
        else:
            raise ConnectionError
    
    def deleteSubPage(self, subcode):
        '''Delete sub-page in open page.
        
        :return: Number of sub pages in page.
        
        :param subcode: hexadecimal sub-code number.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no page open.
        :raise ValueError: Invalid subcode.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__page is None:
                raise RuntimeError('No page open')
            if subcode < 0 or subcode > 0x3F7E or subcode & 0xC080:
                raise ValueError('Invalid subcode')
            res = self.__send(__Command__.PAGEDELSUB + bytes([subcode >> 8, subcode & 0xff]))
            self.__subpage = None # sending this command deselected any subpage
            if res[0] == __Error__.CMDNOENT:
                # don't raise an exception because the end result is the same
                msg = 'Subpage {0:04X} not found in service'.format(subcode)
                warnings.warn(msg) 
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return (res[1] << 8) | res[2] # return number of subpages
        else:
            raise ConnectionError
    
    def closePage(self):
        '''Close currently open page.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, or invalid channel.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            res = self.__send(__Command__.PAGECLOSE)
            if res[0] == __Error__.CMDNOENT:
                # don't raise an exception because the end result is the same
                msg = 'no currently open page'
                warnings.warn(msg)
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            self.__page = None # Command closed any open page
            self.__subpage = None # which cleared any subpage
        else:
            raise ConnectionError
    
    def setPageFunctionCoding(self, function, coding):
        '''Set function and coding variables of open page.
        
        :param function: page function number from 0 to 11.
        :param  coding: page coding number from 0 to 5.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no page open.
        :raise ValueError: Invalid page function or coding.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__page is None:
                raise RuntimeError('No page open')
            if function < 0 or function > 11:
                raise ValueError('Invalid page function')
            if coding < 0 or coding > 5:
                raise ValueError('Invalid page coding')
            res = self.__send(__Command__.PAGEFANDC + bytes([function, coding]))
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    def getPageFunctionCoding(self):
        '''Read function and coding variables of open page
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no page open.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__page is None:
                raise RuntimeError('No page open')
            res = self.__send(__Command__.PAGEFANDC)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return namedtuple('FunctionAndCoding', 'function coding')(res[1], res[2])
        else:
            raise ConnectionError
    
    def setSubPageOptions(self, erase=None, newsflash=None, subtitle=None, suppressHeader=None, update=None, interruptedSequence=None, inhibit=None, transmitPage=None, language=None, region=None, cycleTime=None, timedMode=None):
        '''Set control flags and cycle timings for selected sub-page.
        
        All arguments are optional. If any are undefined the current state of those values is read from the server.
        
        :return: Named tuple containing new page options.
        
        :param erase: C4 Page Erase flag.
        :param newsflash: C5 Newsflash flag.
        :param subtitle: C6 Subtitle flag.
        :param suppressHeader: C7 Suppress Header flag.
        :param update: C8 Update Indicator flag.
        :param interruptedSequence: C9 Interrupted Sequence flag.
        :param inhibit: C10 Inhibit Display flag.
        :param transmitPage: subpage on air flag.
        :param language: C12-14 national option character subset value.
        :param region: character set region.
        :param cycleTime: carousel cycle time in magazine cycles or seconds.
        :param timedMode: flag indicating cycle time represents seconds.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no sub-page selected.
        :raise ValueError: Invalid language or region.
        :raise VersionError: Server version is too old for this command.
        '''
        args = dict(locals())
        del args["self"]
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            
            if None in args.values(): # one or more arguments are not set
                old = self.getSubPageOptions() # read previous values from server
            
            for k,v in args.items():
                # loop through arguments
                if v is None:
                    # use old value for this argument
                    args[k] = getattr(old, k)
            
            if args['language'] < 0 or args['language'] > 7:
                raise ValueError('Invalid language')
            if args['region'] < 0 or args['region'] > 10:
                raise ValueError('Invalid region')
            
            status = bool(args['erase'])<<14 | bool(args['newsflash']) | bool(args['subtitle'])<<1 | bool(args['suppressHeader'])<<2 | bool(args['update'])<<3 | bool(args['interruptedSequence'])<<4 | bool(args['inhibit'])<<5 | bool(args['transmitPage'])<<15 | args['language']<<7
            res = self.__send(__Command__.PAGEOPTNS + bytes([status >> 8, status & 0xff, args['region'], args['cycleTime'], bool(args['timedMode'])]))
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return namedtuple('SubpageOptions', 'erase newsflash subtitle suppressHeader update interruptedSequence inhibit transmitPage language region cycleTime timedMode')(bool(status&0x4000), bool(status&0x0001), bool(status&0x0002), bool(status&0x0004), bool(status&0x0008), bool(status&0x0010), bool(status&0x0020), bool(status&0x8000), (status>>7)&7, args['region'], args['cycleTime'], bool(args['timedMode'])) # return the settings we just wrote
        else:
            raise ConnectionError
    def getSubPageOptions(self):
        '''Read control flags and cycle timings for selected sub-page.
        
        :return: named tuple containing current page options.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no sub-page selected.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            res = self.__send(__Command__.PAGEOPTNS)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            status = (res[1] << 8) | res[2] # page status bits
            return namedtuple('SubpageOptions', 'erase newsflash subtitle suppressHeader update interruptedSequence inhibit transmitPage language region cycleTime timedMode')(bool(status&0x4000), bool(status&0x0001), bool(status&0x0002), bool(status&0x0004), bool(status&0x0008), bool(status&0x0010), bool(status&0x0020), bool(status&0x8000), (status>>7)&7, res[3], res[4], res[5]==1)
        else:
            raise ConnectionError
    
    def getRow(self, number, designationCode=None):
        '''Read row data for row in selected sub-page.
        
        :return: 40 bytes of packet data in relevant VBIT2 row encoding.
        
        :param number: row number in range 1 to 28.
        :param designationCode: packet designation code in range 0 to 15 for rows > 25.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, no sub-page selected, or row does not exist.
        :raise ValueError: Invalid row number or designation code.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            if number < 1 or number > 28:
                raise ValueError('Invalid row number')
            if number < 26:
                res = self.__send(__Command__.PAGEROW + bytes([number]))
            elif designationCode is None or designationCode < 0 or designationCode > 15:
                raise ValueError('Invalid designation code')
            else:
                res = self.__send(__Command__.PAGEROW + bytes([number, designationCode]))
            if res[0] == __Error__.CMDNOENT:
                raise RuntimeError('Row does not exist')
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            return bytes(res[1:41])
        else:
            raise ConnectionError
    
    def setRow(self, number, data):
        '''Write row data to row in selected sub-page.
        
        :param number: row number in range 1 to 28.
        :param data: bytes or bytearray containing exactly 40 bytes using appropriate VBIT2 row encoding.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no sub-page selected.
        :raise TypeError: Invalid data type.
        :raise ValueError: Invalid row number or data length.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            if number < 1 or number > 28:
                raise ValueError('Invalid row number')
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be bytes or bytearray')
            if len(data) != 40:
                 raise ValueError('Must be exactly 40 bytes')
            res = self.__send(__Command__.PAGEROW + bytes([number]) + data)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def deleteRow(self, number, designationCode=None):
        '''Delete row(s) from selected sub-page.
        
        If no designation code is specified for rows greater than 25, all packets with that row number are removed.
        
        :param number: row number in range 1 to 28
        :param designationCode: optional packet designation code in range 0 to 15 for rows > 25
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no sub-page selected.
        :raise ValueError: Invalid row number or designation code.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            if number < 1 or number > 28:
                raise ValueError('Invalid row number')
            if number < 26 or designationCode is None:
                res = self.__send(__Command__.PAGEROW + bytes([0x80 | number]))
            else:
                if designationCode < 0 or designationCode > 15:
                    raise ValueError('Invalid designation code')
                res = self.__send(__Command__.PAGEROW + bytes([0x80 | number, designationCode]))
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def setFastext(self, pages, subcodes=None):
        '''Set navigation packet data for the selected sub-page.
        
        :param pages: list of exactly six hexadecimal page numbers.
        :param subcodes: optional list of exactly six hexadecimal page sub-codes.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, or no sub-page selected.
        :raise TypeError: Invalid pages or subcodes.
        :raise ValueError: Invalid page number or sub-code.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            if not (isinstance(pages, list) and len(pages) == 6):
                raise TypeError('Must be list of six page numbers')
            b = bytearray()
            for p in pages:
                if p < 0x100 or p > 0x8FF:
                    raise ValueError('Invalid page number')
                b.append((p >> 8) & 7); # mag 8 -> mag 0
                b.append(p & 0xff);
            if not subcodes is None:
                if not (isinstance(pages, list) and len(pages) == 6):
                    raise TypeError('Must be list of six subcodes')
                for s in subcodes:
                    if s < 0 or s > 0x3F7F or s & 0xC080:
                        raise ValueError('Invalid subcode')
                    b.append(s >> 8);
                    b.append(s & 0xff);
            res = self.__send(__Command__.PAGELINKS + b)
            if res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
        else:
            raise ConnectionError
    
    def getFastext(self):
        '''Read navigation packet data of the selected sub-page.
        
        :return: named tuple containing list of page numbers and list of sub-codes.
        
        :raise ConnectionError: No connection to server.
        :raise RuntimeError: Server returned an unexpected error, invalid channel, no sub-page selected, or row does not exist.
        :raise VersionError: Server version is too old for this command.
        '''
        if not self.__sock is None:
            if self.__version < (1, 0, 0):
                raise VersionError('Command not supported by this server')
            if self.__chan is None or self.__chan != 0:
                raise RuntimeError('Invalid channel')
            if self.__subpage is None:
                raise RuntimeError('No subpage selected')
            res = self.__send(__Command__.PAGELINKS)
            if res[0] == __Error__.CMDNOENT:
                raise RuntimeError('Fastext link row does not exist')
            elif res[0] != __Error__.CMDOK:
                raise RuntimeError('Server returned unexpected error')
            pages = []
            subcodes = []
            for l in range(0,6):
                p = (res[l*2+1] << 8) | res[l*2+2]
                if p < 0x100:
                    p |= 0x800 # mag 0 -> mag 8
                pages.append(p)
                subcodes.append((res[l*2+13] << 8) | res[l*2+14])
            return namedtuple('Links', 'pages subcodes')(pages, subcodes)
        else:
            raise ConnectionError