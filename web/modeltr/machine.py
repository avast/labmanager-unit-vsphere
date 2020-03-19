from web.settings import Settings as settings

from .base import trString, trList, trId, trSaveTimestamp
from .base_enum import UnitEnumBase
from .document import *

class MachineState(UnitEnumBase):

    CREATED = 'created'
    DEPLOYED = 'deployed'
    RUNNING = 'running'
    STOPPED = 'stopped'
    UNDEPLOYED = 'undeployed'
    FAILED = 'failed'

    def can_be_changed(self) -> bool:
        """
        Machine state cannot be changed for failed and undeployed machines
        :return: bool
        """
        return self not in [MachineState.UNDEPLOYED, MachineState.FAILED]


class Machine(Document):
    unit = trString
    modified_at = trSaveTimestamp
    labels = trList
    custom_machine_name = trString
    state = trString
    provider_id = trString
    requests = trList
    ip_addresses = trList
    nos_id = trString
    machine_name = trString
    machine_search_link = trString
    screenshots = trList
    snapshots = trList

    _defaults = {
                    'state': 'created',
                    'unit': settings.app['unit_name'],
                    'labels': [],
                    'ip_addresses': [],
                    'nos_id': '',
                    'machine_name': '',
                    'machine_search_link': '',
                    'screenshots': [],
                    'snapshots': [],
                }
