from sanic.exceptions import abort
from sanic.response import json as sjson
from sanic import Blueprint

import web.modeltr as data

import web.middleware.obtain_request
import sanic.exceptions
import json
from web.settings import Settings as settings

import sys
import threading
import asyncio
import logging

logger = logging.getLogger(__name__)

capabilities = Blueprint('capabilities')


@capabilities.route('/capabilities', methods=['GET'])
async def cap_get_info(request):
    count = 0
    with data.Connection.use() as conn:
        count = len(data.Machine.get({'state': 'running'}, conn=conn)) + \
            len(data.Machine.get({'state': 'stopped'}, conn=conn)) + \
            len(data.Machine.get({'state': 'deployed'}, conn=conn))
    return {
        'result': {
            'slot_limit': settings.app['slot_limit'],
            'free_slots': settings.app['slot_limit'] - count,
            'labels': settings.app['labels']
        },
        'is_last': True
    }
