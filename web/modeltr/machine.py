from web.settings import Settings as settings

from .base import trString, trList, trId, trSaveTimestamp, trMachineState, trTimestamp, trHiddenString
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

    _defaults = {
                    'state': MachineState.CREATED,
                    'unit': settings.app['unit_name'],
                    'labels': [],
                    'created_at': '',
                    'ip_addresses': [],
                    'nos_id': '',
                    'machine_name': '',
                    'machine_search_link': '',
                    'screenshots': [],
                    'snapshots': [],
                    'owner': '<not_def>',
                }
