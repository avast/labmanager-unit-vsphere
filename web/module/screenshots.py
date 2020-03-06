from sanic import Blueprint
import web.modeltr as data
import logging
from sanic.response import json as sjson

logger = logging.getLogger(__name__)


screenshots = Blueprint('screenshots')


@screenshots.route('/machines/<machine_id>/screenshots', methods=['POST'])
async def take_screenshot(request, machine_id):
    with data.Connection.use() as conn:
        machine = data.Machine.get_one_for_update({'_id': machine_id}, conn=conn)

        new_screenshot = data.Screenshot(machine='{}'.format(machine_id))
        new_screenshot.save(conn=conn)

        machine.screenshots.append(new_screenshot.id)
        machine.save(conn=conn)

        new_request = data.Request(state='created', type='take_screenshot')
        new_request.machine = str(machine.id)
        new_request.subject_id = str(new_screenshot.id)
        new_request.save(conn=conn)

        # begin screenshot preparation
        data.Action(type='other', request=new_request.id).save(conn=conn)
    return {
        'result': {
            'screenshot_id': '{}'.format(new_screenshot.id),
        },
        'is_last': True,
    }


@screenshots.route('/machines/<machine_id>/screenshots/<screenshot_id>', methods=['GET'])
async def get_screenshot(request, machine_id, screenshot_id):
    screenshot = {}
    with data.Connection.use() as conn:
        screenshot = data.Screenshot.get({'_id': screenshot_id}, conn=conn).first()
    return sjson(
        {
            'responses': [{
                'result': {
                    'screenshot_id': f'{screenshot_id}',
                    'base64_data': screenshot.image_base64,
                    'suffix': screenshot.file_type,
                    'status': screenshot.status,
                },
                'type': 'retry_until_last',
                'is_last': False if screenshot.status == 'not_obtained' else True,
            }]
        },
        status=200
    )
