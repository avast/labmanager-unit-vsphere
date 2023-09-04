from .base import trInt, trTimestamp, trSaveTimestamp, trString, trBool
from .document import *


class DeployTicket(Document):
    modified_at = trSaveTimestamp
    created_at = trTimestamp
    taken = trLock
    host_moref = trString
    enabled = trBool
    assigned_vm_moref = trString

    _defaults = {
        'taken':        0,
        'created_at': trTimestamp.NOT_INITIALIZED,
        'enabled': False,
    }
