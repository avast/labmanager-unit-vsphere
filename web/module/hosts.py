import logging
import time
import asyncio
from sanic import Blueprint
import web.modeltr as data
from web.settings import Settings
import sanic.exceptions

hosts = Blueprint('hosts')


@hosts.route('/hosts', methods=['GET'])
async def hosts_get_info(request):
    with data.Connection.use() as conn:
        await asyncio.sleep(0.0)
        result = []
        for host in data.HostRuntimeInfo.get({}, conn=conn):
            hhost = host.to_dict(redacted=True)
            hhost['id'] = host.id
            result.append({
                key: val for key, val in hhost.items() if
                key != "local_datastores" and key != "local_templates"
             })
        return {
            'result': {
                'hosts': result,
            },
            'is_last': True
        }


@hosts.route('/hosts/<host_id>', methods=['GET'])
async def host_get_info(request, host_id):
    with data.Connection.use() as conn:
        await asyncio.sleep(0.0)
        host = data.HostRuntimeInfo.get_one({'_id': host_id}, conn=conn)
        hhost = host.to_dict()
        hhost['id'] = host.id
        return {
            'result': {
                key: val for key, val in hhost.items() if
                key != "local_datastores" and key != "local_templates"
             },
            'is_last': True
        }


@hosts.route('/hosts/<host_id>', methods=['PUT'])
async def host_put(request, host_id):
    action = request.headers.get('json_params').get('action')
    future_maintenance_flag = True
    if action not in ['enter_maintenance', 'leave_maintenance']:
        raise sanic.exceptions.InvalidUsage(
            'malformed input json data, invalid or none \'action\' specified'
        )
    else:
        if action == "enter_maintenance":
            future_maintenance_flag = True
        if action == "leave_maintenance":
            future_maintenance_flag = False

    with data.Connection.use() as conn:
        await asyncio.sleep(0.0)
        host = data.HostRuntimeInfo.get_one_for_update({'_id': host_id}, conn=conn)
        host.to_be_in_maintenance = future_maintenance_flag
        host.save(conn=conn)

        # TODO: start enter maintenance | leave maintenance process

        return {
            'is_last': True
        }