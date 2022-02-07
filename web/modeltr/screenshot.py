from .base import trString, trTimestamp
from .document import *


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
