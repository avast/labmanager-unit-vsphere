from .base import trInt, trTimestamp
from .document import *


class Action(Document):
    modified_at = trSaveTimestamp
    type = trString
    request = trString
    lock = trLock
    repetitions = trInt
    delay = trInt
    next_try = trTimestamp

    _defaults = {
        'type':        'other',
        'lock':        0,
        'repetitions': 0,
        'delay':       5,
        'next_try':    datetime.datetime(year=datetime.MAXYEAR, month=1, day=1)
    }
