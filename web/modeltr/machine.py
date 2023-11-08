from web.settings import Settings

from .base import trString, trList, trSaveTimestamp, trMachineState, trTimestamp, trHiddenString
from .enums import MachineState
from .document import *


class Machine(Document):
    unit = trString
    modified_at = trSaveTimestamp
    created_at = trTimestamp
    labels = trList
    custom_machine_name = trString
    state = trMachineState
    provider_id = trString
    requests = trList
    ip_addresses = trList
    nos_id = trString
    machine_name = trString
    machine_search_link = trString
    screenshots = trList
    snapshots = trList
    owner = trHiddenString
    machine_moref = trString

    _defaults = {
                    'state': MachineState.CREATED,
                    'unit': Settings.app['unit_name'],
                    'labels': [],
                    'created_at': trTimestamp.NOT_INITIALIZED,
                    'ip_addresses': [],
                    'nos_id': '',
                    'machine_name': '',
                    'machine_search_link': '',
                    'screenshots': [],
                    'snapshots': [],
                    'owner': '<not_def>',
                    'machine_moref': "vm-notset"
                }

    def has_feat_running_label(self) -> bool:
        return 'feat:running' in self.labels
