from copy import copy
from decimal import DecimalTuple
import math

from hwt.doc_markers import internal
from hwt.hdl.const import HConst
from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.defs import BOOL
from hwt.hdl.types.typeCast import toHVal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from pyMathBitPrecise.floatt import FloattVal


_HBoolConst = BOOL.getConstCls()


def _HFloatEq(self, self_is_val: bool, other):
    other = toHVal(other, self._dtype)
    other_is_val = isinstance(self, HConst)

    if self_is_val and other_is_val:
        return _HBoolConst(BOOL, int(self.val == other.val), self.vld_mask & other.vld_mask)
    else:
        assert self._dtype == other._dtype, (self, self._dtype, other, other._dtype)
        return HOperatorNode.withRes(HwtOps.EQ, [self, other], BOOL)


class HFloatRtlSignal(RtlSignal):

    def _eq(self, other):
        return _HFloatEq(self, False, other)


class HFloatConst(HConst, FloattVal):
    """
    HConst class for HFloat type.
    """

    @classmethod
    def from_py(cls, typeObj, val, vld_mask=None):
        assert vld_mask is None, vld_mask
        if isinstance(val, int):
            val = float(val)
            if float(val) != val:
                raise NotImplementedError("Need to implement better conversion method")

        if val is None:
            sign = 0
            exp = 0
            man = 0
            assert vld_mask is None or vld_mask == 0
            vld_mask = 0
        elif isinstance(val, float):
            man, exp = math.frexp(val)
            man = abs(man)
            man = int(man * (2 ** typeObj.mantisa_w))
            sign = int(val < 0)
            if vld_mask is None:
                vld_mask = 1
        elif isinstance(val, tuple):
            sign, man, exp = val
            if vld_mask is None:
                vld_mask = 1
        else:
            raise TypeError(val)

        return cls(typeObj, DecimalTuple(sign, man, exp), vld_mask)

    def _is_full_valid(self):
        return self.vld_mask == 1

    def to_py(self):
        """
        Convert to python slice object
        """
        return float(self)

    def _eq(self, other):
        return _HFloatEq(self, True, other)

    def __copy__(self):
        v = HConst.__copy__(self)
        v.val = copy(v.val)
        return v

    @internal
    def __hash__(self):
        v = self.val
        return hash((self._dtype, v))
