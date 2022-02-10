from .base import trString, trSaveTimestamp, trRequestState, trRequestType
from .enums import RequestState
from .document import *


class Request(Document):
    modified_at = trSaveTimestamp
    type = trRequestType
    state = trRequestState
    machine = trString
    subject_id = trString

    _defaults = {
                    'state': RequestState.CREATED
                }
