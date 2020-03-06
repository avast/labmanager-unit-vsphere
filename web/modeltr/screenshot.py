import web.settings
import datetime
from .base import trString, trList, trId, trSaveTimestamp, trTimestamp
from .document import *
import logging


class Screenshot(Document):
    created_at = trTimestamp
    file_type = trString
    image_base64 = trString
    machine = trString
    status = trString

    _defaults = {
                    'file_type': 'png',
                    'status': 'not_obtained',
                }
