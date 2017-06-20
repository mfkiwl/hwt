from hwt.hdlObjects.constants import DIRECTION
from hwt.hdlObjects.typeShortcuts import vecT
from hwt.hdlObjects.types.bits import Bits
from hwt.hdlObjects.types.defs import BIT, BIT_N
from hwt.interfaces.signalOps import SignalOps
from hwt.synthesizer.interfaceLevel.interface import Interface
from hwt.synthesizer.param import Param, evalParam
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase


D = DIRECTION


class Signal(SignalOps, Interface):
    """
    Basic wire interface
    """
    def __init__(self,
                 masterDir=D.OUT,
                 asArraySize=None,
                 dtype=BIT,
                 loadConfig=True):
        super().__init__(masterDir=masterDir,
                         asArraySize=asArraySize,
                         loadConfig=loadConfig)
        self._dtype = dtype

    def _injectMultiplerToDtype(self):
        """
        Make signal wider, used when there is an array of signals stored in one wider signal
        """
        t = self._dtype
        factor = self._widthMultiplier
        if t == BIT:
            newT = vecT(factor)
        elif isinstance(t, Bits):
            w = t.width
            if isinstance(w, int):
                newW = factor * w
            elif isinstance(w, RtlSignalBase):
                # both Param or factor Value
                newW = w * factor
            elif isinstance(factor, RtlSignalBase):
                # w is Value
                newW = factor * w
            else:
                # both Value
                newW = w.clone()
                newW.val *= factor.val
            newT = vecT(newW)
        else:
            raise TypeError("Can not multiply width of type %r" % (repr(t),))

        self._dtype = newT

    def _getSimAgent(self):
        from hwt.interfaces.agents.signal import SignalAgent
        return SignalAgent


def VectSignal(width,
               signed=None,
               masterDir=D.OUT,
               asArraySize=None,
               loadConfig=True):
    """
    Create basic :class:`.Signal` interface where type is vector
    """
    return Signal(masterDir,
                  asArraySize,
                  vecT(width, signed),
                  loadConfig)


class Clk(Signal):
    """
    Basic :class:`.Signal` interface which is interpreted as clock signal
    """
    def _getIpCoreIntfClass(self):
        from hwt.serializer.ip_packager.interfaces.std import IP_Clk
        return IP_Clk

    def _getSimAgent(self):
        from hwt.interfaces.agents.clk import OscilatorAgent
        return OscilatorAgent


class Rst(Signal):
    """
    Basic :class:`.Signal` interface which is interpreted as reset signal
    """
    def _getIpCoreIntfClass(self):
        from hwt.serializer.ip_packager.interfaces.std import IP_Rst
        return IP_Rst

    def _getSimAgent(self):
        from hwt.interfaces.agents.rst import PullDownAgent
        return PullDownAgent


class Rst_n(Signal):
    """
    Basic :class:`.Signal` interface which is interpreted as reset signal with negative polarity (active in 0)
    """
    def __init__(self,
                 masterDir=D.OUT,
                 asArraySize=None,
                 dtype=BIT_N,
                 loadConfig=True):
        super(Rst_n, self).__init__(masterDir=D.OUT,
                                    asArraySize=asArraySize,
                                    dtype=dtype,
                                    loadConfig=dtype)

    def _getIpCoreIntfClass(self):
        from hwt.serializer.ip_packager.interfaces.std import IP_Rst_n
        return IP_Rst_n

    def _getSimAgent(self):
        from hwt.interfaces.agents.rst import PullUpAgent
        return PullUpAgent


class VldSynced(Interface):
    """
    Interface data+valid signal, if vld=1 then data are valid and slave should accept them
    """
    def _config(self):
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        self.data = s(dtype=vecT(self.DATA_WIDTH))
        self.vld = s()

    def _getSimAgent(self):
        from hwt.interfaces.agents.vldSynced import VldSyncedAgent
        return VldSyncedAgent


class RdSynced(Interface):
    """
    Interface data+ready signal, if rd=1 then slave has read data and master should actualize data
    """
    def _config(self):
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        self.data = s(dtype=vecT(self.DATA_WIDTH))
        self.rd = s(masterDir=D.IN)

    def _getSimAgent(self):
        from hwt.interfaces.agents.rdSynced import RdSyncedAgent
        return RdSyncedAgent


class Handshaked(VldSynced):
    """
    Interface data+ready+valid signal, if rd=1 slave is ready to accept data, if vld=1 master is sending data,
    if rd=1 and vld=1 then data is transfered otherwise master and slave has to wait on each other
    :attention: one rd/vld is set it must not go down until transaction is made
    """
    def _declr(self):
        super()._declr()
        self.rd = s(masterDir=D.IN)

    def _getSimAgent(self):
        from hwt.interfaces.agents.handshaked import HandshakedAgent
        return HandshakedAgent


class HandshakeSync(Interface):
    """
    Only synchronization interface, like vld+rd signal with meaning like in :class:`.Handshaked` interface
    
    :ivar rd: when high slave is ready to receive data
    :ivar vld: when high master is sending data to slave

    transaction happens when both ready and valid are high

    """
    def _declr(self):
        self.vld = s()
        self.rd = s(masterDir=D.IN)

    def _getSimAgent(self):
        from hwt.interfaces.agents.handshaked import HandshakeSyncAgent
        return HandshakeSyncAgent


class ReqDoneSync(Interface):
    """
    Synchronization interface, if req=1 slave begins operation and when its done it asserts done=1 for one clk tick
    req does not need to stay high
    """
    def _declr(self):
        self.req = s()
        self.done = s(masterDir=D.IN)


class BramPort_withoutClk(Interface):
    """
    Basic BRAM port
    """
    def _config(self):
        self.ADDR_WIDTH = Param(32)
        self.DATA_WIDTH = Param(64)

    def _declr(self):
        self.addr = s(dtype=vecT(self.ADDR_WIDTH))
        self.din = s(dtype=vecT(self.DATA_WIDTH))
        self.dout = s(masterDir=D.IN, dtype=vecT(self.DATA_WIDTH))
        self.en = s()
        self.we = s()

    def _getIpCoreIntfClass(self):
        from hwt.serializer.ip_packager.interfaces.std import IP_BlockRamPort
        return IP_BlockRamPort

    def _getSimAgent(self):
        from hwt.interfaces.agents.bramPort import BramPort_withoutClkAgent
        return BramPort_withoutClkAgent

    def _getWordAddrStep(self):
        """
        :return: size of one word in unit of address
        """
        return 1

    def _getAddrStep(self):
        """
        :return: how many bits is one unit of address (f.e. 8 bits for  char * pointer,
             36 for 36 bit bram)
        """
        return evalParam(self.DATA_WIDTH).val


class BramPort(BramPort_withoutClk):
    """
    BRAM port with it's own clk
    """
    def _declr(self):
        self.clk = s(masterDir=D.OUT)
        with self._associated(clk=self.clk):
            super()._declr()

        self._associatedClk = self.clk

    def _getSimAgent(self):
        from hwt.interfaces.agents.bramPort import BramPortAgent
        return BramPortAgent

    @classmethod
    def fromBramPort_withoutClk(cls, bramPort, clk):
        assert isinstance(bramPort, BramPort_withoutClk)
        assert isinstance(clk, Clk)
        self = cls()
        rp = self._replaceParam

        def setIntf(name, intf):
            setattr(self, name, intf)
            self._interfaces.append(intf)

        rp("ADDR_WIDTH", bramPort.ADDR_WIDTH)
        rp("DATA_WIDTH", bramPort.DATA_WIDTH)

        self._interfaces = []
        for iName in ["addr", "din", "dout", "en", "we"]:
            intf = getattr(bramPort, iName)
            setIntf(iName, intf)
        setIntf("clk", clk)

        return self


class FifoWriter(Interface):
    def _config(self):
        self.DATA_WIDTH = Param(8)

    def _declr(self):
        self.en = s()
        self.wait = s(masterDir=D.IN)
        self.data = s(dtype=vecT(self.DATA_WIDTH))

    def _getSimAgent(self):
        from hwt.interfaces.agents.fifo import FifoWriterAgent
        return FifoWriterAgent


class FifoReader(FifoWriter):
    def _declr(self):
        super()._declr()
        self.en._masterDir = D.IN
        self.wait._masterDir = D.OUT

    def _getSimAgent(self):
        from hwt.interfaces.agents.fifo import FifoReaderAgent
        return FifoReaderAgent


class RegCntrl(Interface):
    """
    Register control interface, :class:`.Signal` for read, :class:`.VldSynced` for write
    """
    def _config(self):
        self.DATA_WIDTH = Param(8)

    def _declr(self):
        self.din = Signal(dtype=vecT(self.DATA_WIDTH), masterDir=D.IN)
        with self._paramsShared():
            self.dout = VldSynced()

    def _getSimAgent(self):
        from hwt.interfaces.agents.regCntrl import RegCntrlAgent
        return RegCntrlAgent

s = Signal
