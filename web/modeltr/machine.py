from web.settings import Settings as settings

from .base import trString, trList, trId, trSaveTimestamp
from .document import *


class Machine(Document):
    unit = trString
    modified_at = trSaveTimestamp
    labels = trList
    custom_machine_name = trString
    state = trString
    provider_id = trString
    requests = trList
    ip_addresses = trList

    _defaults = {
                    'state': 'created',
                    'unit': settings.app['unit_name'],
                    'labels': [],
                    'ip_addresses': []
                }
