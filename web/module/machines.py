from web.settings import Settings as settings
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


async def check_payload_deploy(request):
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
    return {
            'exception': '|'.join(exception.args),
    }


@machines.route('/machines', methods=['POST'])
async def machine_deploy(request):
    await check_payload_deploy(request)
    logger.debug("POST /machines wanted by: {}".format(request.headers["AUTHORISED_LOGIN"]))
    with data.Connection.use() as conn:
        new_request = data.Request(type=data.RequestType.DEPLOY)
        new_request.save(conn=conn)
        if settings.app['service']['personalised']:
            new_machine = data.Machine(
                labels=request.headers['json_params']['labels'],
                requests=[new_request.id],
                owner=request.headers["AUTHORISED_LOGIN"],
            )
        else:
            new_machine = data.Machine(
                labels=request.headers['json_params']['labels'],
                requests=[new_request.id]
            )
        new_machine.save(conn=conn)

        new_request.machine = str(new_machine.id)
        new_request.save(conn=conn)

        # begin machine preparation
        data.Action(type='deploy', request=new_request.id).save(conn=conn)

    return {
            'request_id': '{}'.format(new_request.id),
            'is_last': False
    }


async def get_machines(request, connection, **kwargs):
    raw_args = request.raw_args
    if 'flt' in kwargs:
        raw_args = {**raw_args, **kwargs['flt']}
    if settings.app['service']['personalised'] and \
       request.headers.get("AUTHORISED_AS", "None") == "user":
        return data.Machine.get(
            {**raw_args, **{'owner': request.headers["AUTHORISED_LOGIN"]}},
            conn=connection
        )
    else:
        return data.Machine.get(raw_args, conn=connection)


async def show_hidden_strings(request):
    return request.headers.get("AUTHORISED_AS", "None") == "admin"


@machines.route('/machines', methods=['GET'])
async def machines_get_info(request):
    for key in request.raw_args.keys():
        if key not in ['state']:
            raise sanic.exceptions.InvalidUsage(
                'malformatted parameter: {}'.format(key)
            )

    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        machines = await get_machines(request, conn)
        output = []
        for machine in machines:
            output.append({
                **machine.to_dict(show_hidden=await show_hidden_strings(request)),
                **{'id': machine.id}
            })

    return {
            'result': output,
            'is_last': True
    }


@machines.route('/machines/<machine_id>', methods=['GET'])
async def machine_get_info(request, machine_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))
    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        try:
            req = (await get_machines(request, conn, flt={'_id': machine_id})).first()
            result = req.to_dict(show_hidden=await show_hidden_strings(request))
        except Exception as ex:
            raise sanic.exceptions.InvalidUsage("Specified resource cannot be obtained")
    return {
            'result': result,
            'is_last': True
    }


async def check_machine_owner(machine, request):
    if machine is None:
        raise sanic.exceptions.InvalidUsage("Specified resource cannot be obtained")
    if request.headers.get("AUTHORISED_AS", "None") == "admin":
        return
    if settings.app['service']['personalised'] and \
       machine.owner != request.headers["AUTHORISED_LOGIN"]:
        raise sanic.exceptions.InvalidUsage("Specified resource cannot be altered")


@machines.route('/machines/<machine_id>', methods=['DELETE'])
async def machine_get_info(request, machine_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        machine = data.Machine.get_one_for_update({'_id': machine_id}, conn=conn)
        await check_machine_owner(machine, request)
        new_request = data.Request(type=data.RequestType.UNDEPLOY, machine=str(machine_id))
        new_request.save(conn=conn)
        machine.requests.append(new_request.id)
        machine.save(conn=conn)
        data.Action(type='other', request=new_request.id).save(conn=conn)

    return {
            'request_id': '{}'.format(new_request.id),
            'is_last': False
    }


@machines.route('/machines/<machine_id>', methods=['PUT'])
async def machine_do_start_stop(request, machine_id):
    logger.debug('Current thread name: {}'. format(threading.current_thread().name))

    action = request.headers.get('json_params').get('action')
    if action not in ['start', 'stop']:
        raise sanic.exceptions.InvalidUsage('malformatted input json data, invalid or none \'action\' specified')

    request_type = data.RequestType(action)

    # do start / stop
    with data.Connection.use() as conn:
        asyncio.sleep(0.1)
        machine = data.Machine.get_one_for_update({'_id': machine_id}, conn=conn)
        await check_machine_owner(machine, request)
        new_request = data.Request(type=request_type, machine=str(machine_id))
        new_request.save(conn=conn)
        machine.requests.append(new_request.id)
        machine.save(conn=conn)
        data.Action(type='other', request=new_request.id).save(conn=conn)

    return {
            'request_id': '{}'.format(new_request.id),
            'is_last': False
    }
