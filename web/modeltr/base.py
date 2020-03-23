import datetime
from .enums import MachineState

__all__ = ['trString', 'trList', 'trId', 'trSaveTimestamp', 'trLock', 'trInt', 'trTimestamp', 'trMachineState']


class trString(object):
    _default = ''
    _type = type(_default)


class trLock(object):
    _default = 0
    _type = type(_default)


class trInt(object):
    _default = 0
    _type = type(_default)


class trId(object):
    _default = '<null>'
    _type = type(_default)


class trList(object):
    _default = []
    _type = type(_default)


class trSaveTimestamp(object):
    _default = datetime.datetime.now()
    _type = type(_default)


class trTimestamp(object):
    _default = datetime.datetime.now()
    _type = type(_default)

# ------------- enums ---------------


class trMachineState:
    _default = MachineState.CREATED
    _type = MachineState
