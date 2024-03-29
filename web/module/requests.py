import asyncio
import logging

from sanic import Blueprint

import web.modeltr as data
from web.module.capabilities import Capabilities
from web.settings import Settings

logger = logging.getLogger(__name__)

requests = Blueprint('requests')


@requests.route('/requests/<req_id>', methods=['GET'])
async def req_get_info(request, req_id):

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
        # add required result data based on request type
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
            await Capabilities.fetch(forced=True)
            extra_result = [{
                               'result': {
                                   'machine_id': req.machine,
                                   'capabilities': {
                                       'slot_limit': Capabilities.get_slot_limit(),
                                       'free_slots': Capabilities.get_free_slots(),
                                       'labels': Capabilities.get_labels(),
                                   },
                               },
                               'is_last': False,
                               'type': 'return_value',
            }]
            result = extra_result + result

        if req.state.is_error():
            unit_name = Settings.app.get('unit_name', 'N/A')
            deploy_error_msg = f'deploy of machine \'{req.machine}\' on unit \'{unit_name}\' failed (request_id: {req_id})'
            generic_error_msg = f'request {req_id} ({str(req.type)}) failed, machine_id: {req.machine}'
            exception_message = deploy_error_msg if req.type is data.RequestType.DEPLOY else generic_error_msg
            result[0]['is_last'] = False
            result.append({
                'exception': exception_message,
                'exception_args': [],
                'exception_traceback': [],
                'is_last': True
            })
            logger.warning(f'Exception block returned for request: {req_id}, type: {req.type} -- {exception_message}')

        if req.state.has_finished() and req.state is not data.RequestState.SUCCESS:
            message = f'Request has finished in state: {str(req.state)}, type: {str(req.type)}'
            logger.warning(message)
            try:
                machine_ro = data.Machine.get_one({'_id': req.machine}, conn=conn)
                logger.warning(f"{message} and machine ({req.machine}) was in state: {machine_ro.state}")
            except Exception:
                pass

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
