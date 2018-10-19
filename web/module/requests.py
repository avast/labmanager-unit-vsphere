from sanic.exceptions import abort
from sanic import Blueprint

import web.modeltr as data

import web.middleware.obtain_request
import sanic.exceptions
import json

import sys
import threading
import asyncio


logger = logging.getLogger(__name__)

requests = Blueprint('requests')


@requests.route('/requests/<req_id>', methods=['GET'])
async def req_get_info(request, req_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    with data.Connection.use() as conn:
        with data.Transaction(conn):
            asyncio.sleep(0.1)
            req = data.Request.get({'_id': req_id}, conn=conn).first()
            return {
                'responses': [
                    {
                        'type': 'return_value',
                        'response_id': '0',
                        'is_last': True,
                        'result': {
                            'machine_id': req.machine,
                            'state': req.state,
                            'type': req.type
                        }
                    }
                ]
            }
