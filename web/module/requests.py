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
from web.module.capabilities import Capabilities as cap
from web.settings import Settings as settings

logger = logging.getLogger(__name__)

requests = Blueprint('requests')


@requests.route('/requests/<req_id>', methods=['GET'])
async def req_get_info(request, req_id):
    # logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    with data.Connection.use() as conn:
        await asyncio.sleep(0.1)
        req = data.Request.get({'_id': req_id}, conn=conn).first()
        result_dict = {
                    'machine_id': req.machine,
                    'state': str(req.state),
                    'request_type': str(req.type),
                    'modified_at': req.to_dict()['modified_at'],
                }

        # TODO solve this better
        # add requited result data based on request type
        if req.type is data.RequestType.TAKE_SNAPSHOT:
            snap_ro = data.Snapshot.get_one({'_id': req.subject_id}, conn=conn)
            result_dict['id'] = snap_ro.id
            result_dict['name'] = snap_ro.name

        result = [
            {
                'result': result_dict,
                'is_last': req.state.has_finished()
            }]

        if req.type is data.RequestType.DEPLOY:
            await cap.fetch(forced=True)
            extra_result = [{
                               'result': {
                                   'machine_id': req.machine,
                                   'capabilities': {
                                       'slot_limit': cap.get_slot_limit(),
                                       'free_slots': cap.get_free_slots(),
                                       'labels': cap.get_labels(),
                                   },
                               },
                               'is_last': False,
                               'type': 'return_value',
            }]
            result = extra_result + result

        if req.state.is_error():
            unit_name = settings.app.get('unit_name', 'N/A')
            deploy_error_msg = 'deploy of machine \'{}\' on unit \'{}\' failed'.format(req.machine, unit_name)
            result[0]['is_last'] = False
            result.append({
                'exception': deploy_error_msg if req.type is data.RequestType.DEPLOY else 'request failed',
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
