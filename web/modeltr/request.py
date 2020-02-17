import web.settings
import datetime
from .base import trString, trList, trId, trSaveTimestamp
from .document import *


class Request(Document):
    modified_at = trSaveTimestamp
    type = trString
    state = trString
    machine = trString
    subject_id = trString

    _defaults = {
                    'state': 'created'
                }
