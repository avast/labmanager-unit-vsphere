from sanic.exceptions import abort
from sanic.response import json as sjson
from sanic import Blueprint

import web.modeltr as data

from web.settings import Settings as settings
from web.modeltr.enums import MachineState

import logging

logger = logging.getLogger(__name__)

capabilities = Blueprint('capabilities')


@capabilities.route('/capabilities', methods=['GET'])
async def cap_get_info(request):
    count = 0
    with data.Connection.use() as conn:
        count = len(data.Machine.get({'state': MachineState.RUNNING.value}, conn=conn)) + \
            round(len(data.Machine.get({'state': MachineState.STOPPED.value}, conn=conn))/2) + \
            len(data.Machine.get({'state': MachineState.DEPLOYED.value}, conn=conn)) + \
            len(data.Machine.get({'state': MachineState.CREATED.value}, conn=conn))
    slot_limit = settings.app['slot_limit']
    free_slots = slot_limit - count if count < slot_limit else 0
    return {
        'result': {
            'slot_limit': slot_limit,
            'free_slots': free_slots,
            'labels': settings.app['labels'] + ["unit:{}".format(settings.app['unit_name'])]
        },
        'is_last': True
    }
