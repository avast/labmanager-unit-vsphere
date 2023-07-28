from web.settings import Settings

from .base import trString, trList, trSaveTimestamp, trTimestamp, trDict, trBool, trInt
from .document import *
from .enums import HostStandbyMode,HostConnectionState


class HostRuntimeInfo(Document):
    modified_at = trSaveTimestamp
    created_at = trTimestamp
    name = trString
    mo_ref = trString               # host-14882398 like string
    maintenance = trBool
    to_be_in_maintenance = trBool
    connection_state = trString     # connected, disconnected, notResponding
    vms_count = trInt
    vms_running_count = trInt
    standby_mode = trString         # entering, exiting, in, none
    local_templates = trList
    local_datastores = trList
    associated_resource_pool = trString

    _defaults = {
        'created_at': trTimestamp.NOT_INITIALIZED,
        'maintenance': True,
        'to_be_in_maintenance': False,
        'connection_state': HostConnectionState.NOTRESPONDING,
        'standby_mode': HostStandbyMode.IN,
    }
