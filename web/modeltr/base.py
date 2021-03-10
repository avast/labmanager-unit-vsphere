import datetime
from .enums import MachineState, RequestState, RequestType

__all__ = [
            'trString',
            'trList',
            'trId',
            'trSaveTimestamp',
            'trLock',
            'trInt',
            'trTimestamp',
            'trMachineState',
            'trRequestState',
            'trRequestType',
            'trHiddenString',
]


class trString(object):
    _default = ''
    _type = type(_default)


class trHiddenString(object):
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


class trRequestState:
    _default = RequestState.CREATED
    _type = RequestState


class trRequestType:
    _default = '<null>'
    _type = RequestType
