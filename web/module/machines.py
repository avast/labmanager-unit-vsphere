from sanic.response import json as sjson
import sanic.response
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

machines = Blueprint('machines')


def check_payload_deploy(request):
    if 'json_params' in request.headers and 'labels' in request.headers['json_params']:
        return True
    raise sanic.exceptions.InvalidUsage(
        'malformatted input json data, field labels must be specified'
    )


@machines.middleware('request')
async def obtain_request(request):
    logger.debug("Request obtained: {}".format(request))


@machines.exception(sanic.exceptions.InvalidUsage)
def handle_exceptions(request, exception):
    return sjson({'error': ''.join(exception.args)}, status=exception.status_code)


@machines.route('/machines', methods=['POST'])
async def machine_deploy(request):
    check_payload_deploy(request)

    with data.Connection.use() as conn:
        new_request = data.Request(state='created', type='deploy')
        new_request.save(conn=conn)

        new_machine = data.Machine(
            labels=request.headers['json_params']['labels'],
            requests=[new_request.id]
        )
        new_machine.save(conn=conn)

        new_request.machine = str(new_machine.id)
        new_request.save(conn=conn)

        # begin machine preparation
        data.Action(type='deploy', request=new_request.id).save(conn=conn)

    return {'request_id': '{}'.format(new_request.id)}


@machines.route('/machines/<machine_id>', methods=['GET'])
async def machine_get_info(request, machine_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        req = data.Machine.get({'_id': machine_id}, conn=conn).first()
        rr = req.to_dict()
        del rr['modified_at']

    return sanic.response.text(json.dumps(rr))


@machines.route('/machines/<machine_id>', methods=['DELETE'])
async def machine_get_info(request, machine_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        machine = data.Machine.get_one_for_update({'_id': machine_id}, conn=conn)
        new_request = data.Request(type='undeploy', machine=str(machine_id))
        new_request.save(conn=conn)
        machine.requests.append(new_request.id)
        machine.save(conn=conn)
        data.Action(type='other', request=new_request.id).save(conn=conn)

    return {'request_id': '{}'.format(new_request.id)}


async def machine_start(request, machine_id):
    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        machine = data.Machine.get_one_for_update({'_id': machine_id}, conn=conn)
        new_request = data.Request(type='start', machine=str(machine_id))
        new_request.save(conn=conn)
        machine.requests.append(new_request.id)
        machine.save(conn=conn)
        data.Action(type='other', request=new_request.id).save(conn=conn)

    return {'request_id': '{}'.format(new_request.id)}


async def machine_stop(request, machine_id):
    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        machine = data.Machine.get_one_for_update({'_id': machine_id}, conn=conn)
        new_request = data.Request(type='stop', machine=str(machine_id))
        new_request.save(conn=conn)
        machine.requests.append(new_request.id)
        machine.save(conn=conn)
        data.Action(type='other', request=new_request.id).save(conn=conn)

    return {'request_id': '{}'.format(new_request.id)}


@machines.route('/machines/<machine_id>', methods=['PUT'])
async def machine_get_info(request, machine_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    if request.headers['json_params']['action'] == 'start':
        return await machine_start(request, machine_id)

    elif request.headers['json_params']['action'] == 'stop':
        return await machine_stop(request, machine_id)

    else:
        raise sanic.exceptions.InvalidUsage(
            'malformatted input json data, field action must be specified'
        )
