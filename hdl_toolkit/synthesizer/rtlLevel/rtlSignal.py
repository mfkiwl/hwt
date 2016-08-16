from hdl_toolkit.hdlObjects.assignment import Assignment, mkArrayUpdater
from hdl_toolkit.hdlObjects.operatorDefs import AllOps
from hdl_toolkit.hdlObjects.portItem import PortItem
from hdl_toolkit.hdlObjects.types.hdlType import HdlType
from hdl_toolkit.hdlObjects.value import Value
from hdl_toolkit.hdlObjects.variables import SignalItem
from hdl_toolkit.simulator.exceptions import SimException
from hdl_toolkit.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hdl_toolkit.synthesizer.rtlLevel.signalUtils.exceptions import MultipleDriversExc
from hdl_toolkit.synthesizer.rtlLevel.signalUtils.ops import RtlSignalOps



def simEvalIndexedAssign(simulator, indexedOn, index, newVal):
    indxVal = index.simEval(simulator)
    # [TODO] multiple nested indexing in assignment
    print(simulator.env.now)
    indexedOn.simUpdateVal(simulator, mkArrayUpdater(newVal, indxVal))
    

class UniqList(list):
    def append(self, obj):
        if obj not in self:
            list.append(self, obj)

class RtlSignal(RtlSignalBase, SignalItem, RtlSignalOps):
    """
    more like net
    @ivar _usedOps: dictionary of used operators which can be reused
    @ivar endpoints: UniqList of operators and statements for which this signal is driver.
    @ivar drivers: UniqList of operators and statements which can drive this signal.
    @ivar negated: this value represents that the value of signal has opposite meaning
           [TODO] mv negated to Bits hdl type.
    @ivar hiden: means that this signal is part of expression and should not be rendered 
    @ivar processCrossing: means that this signal is crossing process boundary
    """
    def __init__(self, name, dtype, defaultVal=None):
        if name is None:
            name = "sig_" + str(id(self))
            self.hasGenericName = True
        else:
            self.hasGenericName = False  
       
        assert isinstance(dtype, HdlType)
        super().__init__(name, dtype, defaultVal)
        # set can not be used because hash of items are changign
        self.endpoints = UniqList()
        self.drivers = UniqList()
        self._usedOps = {}
        self.negated = False
        self.hidden = True
        
        self.simSensitiveProcesses = set()
    
    def simPropagateChanges(self, simulator):
        self._oldVal = self._val

        for e in self.endpoints:
            if isinstance(e, PortItem) and e.dst is not None:
                e.dst.simUpdateVal(simulator, lambda v: (True, self._val))
            else:
                try:
                    isIndexing = e.operator == AllOps.INDEX 
                except AttributeError:
                    isIndexing = False
                
                if isIndexing:
                    if e.result is self:
                        # mem[indx] = self
                        simEvalIndexedAssign(simulator, e.ops[0], e.ops[1], self._val)
                    else:
                        #    result = self[index]
                        # or result = index[self]
                        resSig = e.result
                        if resSig.endpoints: 
                            # because there can be unused operators which can change direction of dataflow
                            # for example when index is constructed we do not know if assignment will come or not,
                            # if it comes original operator is left and reversed is constructed
                            resSig.simEval(simulator)
            
        log = simulator.config.logPropagation
        for p in self.simSensitiveProcesses:        
            if log:
                log(simulator, self, p)
                
            simulator.addHwProcToRun(p, False)
        
    def staticEval(self):
        # operator writes in self._val new value
        if self.drivers:
            for d in self.drivers:
                d.staticEval()
        else:
            if isinstance(self.defaultVal, RtlSignal):
                self._val = self.defaultVal._val.staticEval()
            else:
                if self._val.updateTime < 0:  
                    self._val = self.defaultVal.clone()
        
        if not isinstance(self._val, Value):
            raise SimException("Evaluation of signal returned not supported object (%s)" % 
                               (repr(self._val)))
        return self._val
    
    def simEval(self, simulator):
        """
        Evaluate, signals which have hidden flag set
        @attention: single process has to drive single variable in order to work
        """
        for d in self.drivers:
            if isinstance(d, Assignment):
                continue
            try:
                o = d.operator
                # if I am not driven by this index
                if o == AllOps.INDEX and d.result is not self:
                    continue
            except AttributeError:
                pass
            
            d.simEval(simulator)
            
        if not isinstance(self._val, Value):
            raise SimException("Evaluation of signal returned not supported object (%s)" % 
                               (repr(self._val)))
        return self._val
        
    
    def simUpdateVal(self, simulator, valUpdater):
        """
        Method called by simulator to update new value for this object
        """
        
        dirtyFlag, newVal = valUpdater(self._oldVal)
        self._val = newVal
        newVal.updateTime = simulator.env.now
        
        if dirtyFlag:
            log = simulator.config.logChange
            if  log:
                log(simulator.env.now, self, newVal)
            
            self.simPropagateChanges(simulator)
     
    def singleDriver(self):
        """
        Returns a first driver if signal has only one driver.
        """
        if len(self.drivers) != 1:
            raise MultipleDriversExc()
        return list(self.drivers)[0]

