from sanic.exceptions import abort
from sanic.response import json as sjson
from sanic import Blueprint

import web.modeltr as data

from web.settings import Settings as settings
from web.modeltr.enums import MachineState

import logging
import time

logger = logging.getLogger(__name__)

capabilities = Blueprint('capabilities')


class Capabilities:
    _free_slots = 0
    _slot_limit = settings.app['slot_limit']
    _last_check = 0
    _labels = settings.app['labels'] + ["unit:{}".format(settings.app['unit_name'])]

    @staticmethod
    async def fetch(forced=False):
        used_slots = Capabilities._slot_limit - Capabilities._free_slots
        logger.debug("Capabilities last check: {}".format(Capabilities._last_check))
        caching_period = settings.app['service']['capabilities']['caching_period']
        caching_threshold = settings.app['service']['capabilities']['caching_enabled_threshold']
        if forced or \
           used_slots > int(Capabilities._slot_limit*(caching_threshold/100)) or \
           int(time.time()) - Capabilities._last_check > caching_period:
            logger.debug("Real capabilities fetch from db in progress...")
            used_slots = 0
            with data.Connection.use() as conn:
                used_slots = \
                    len(data.Machine.get({'state': MachineState.RUNNING.value}, conn=conn)) + \
                    round(len(data.Machine.get({'state': MachineState.STOPPED.value}, conn=conn))/2) + \
                    len(data.Machine.get({'state': MachineState.DEPLOYED.value}, conn=conn)) + \
                    len(data.Machine.get({'state': MachineState.CREATED.value}, conn=conn))
            Capabilities._last_check = int(time.time())
            Capabilities._free_slots = max(Capabilities._slot_limit - used_slots, 0)
            logger.debug("Real capabilities fetch finished")

    @staticmethod
    def get_free_slots():
        return Capabilities._free_slots

    @staticmethod
    def get_slot_limit():
        return Capabilities._slot_limit

    @staticmethod
    def get_labels():
        return Capabilities._labels


@capabilities.route('/capabilities', methods=['GET'])
async def cap_get_info(request):
    await Capabilities.fetch()
    return {
        'result': {
            'slot_limit': Capabilities.get_slot_limit(),
            'free_slots': Capabilities.get_free_slots(),
            'labels': Capabilities.get_labels(),
        },
        'is_last': True
    }
