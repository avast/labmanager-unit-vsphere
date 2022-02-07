from .base import trString, trTimestamp
from .document import *


class Snapshot(Document):
    created_at = trTimestamp
    name = trString
    machine = trString
    status = trString

    _defaults = {
                    'status': 'not_created',
                }

    def get_uniq_name(self):
        created_at_str = str(self.created_at).replace(' ', '_')
        return f'{self.name}_{created_at_str}'
