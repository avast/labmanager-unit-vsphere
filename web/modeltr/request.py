import web.settings
import datetime
from .base import trString, trList, trId, trSaveTimestamp, trRequestState
from .enums import RequestState
from .document import *


class Request(Document):
    modified_at = trSaveTimestamp
    type = trString
    state = trRequestState
    machine = trString
    subject_id = trString

    _defaults = {
                    'state': RequestState.CREATED
                }
