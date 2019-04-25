from sanic.exceptions import abort
from sanic import Blueprint

import web.modeltr as data

import web.middleware.obtain_request
import sanic.exceptions
import json

import sys
import threading
import asyncio
import logging

logger = logging.getLogger(__name__)

requests = Blueprint('requests')


@requests.route('/requests/<req_id>', methods=['GET'])
async def req_get_info(request, req_id):
    # logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        req = data.Request.get({'_id': req_id}, conn=conn).first()
        result = [
            {
                'result': {
                    'machine_id': req.machine,
                    'state': req.state,
                    'request_type': req.type
                },
                'is_last': req.state in ['success', 'failed', 'errored']
            }]
        if req.state in ['errored', 'failed']:
            result[0]['is_last'] = False
            result.append({
                'exception': 'request failed',
                'exception_args': [],
                'exception_traceback': [],
                'is_last': True
            })
        return result


@requests.route('/requests', methods=['GET'])
async def req_get_info(request):

    result = [{
                    'result': {
                        'machine_id': 'none',
                        'state': 'none',
                        'request_type': 'none'
                    },
                    'is_last': True
        }]
    return result
