import web.settings
import datetime
from .base import trString, trList, trId, trSaveTimestamp, trTimestamp
from .document import *
import logging


class Snapshot(Document):
    created_at = trTimestamp
    name = trString
    machine = trString
    status = trString

    _defaults = {
                    'status': 'not_created',
                }
