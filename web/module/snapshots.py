from sanic import Blueprint
import web.modeltr as data
import logging
from sanic.exceptions import InvalidUsage
import sanic.response

from sanic import Blueprint

snapshots = Blueprint('snapshots')


# @snapshots.route('/machines/<machine_id>/snapshots', methods=['GET'])
# async def machines_deploy(request, machine_id):
#     return {'check': 'machines_get_snapshots {}, rq: {}'.format(machine_id, request.headers)}

@snapshots.route('/machines/<machine_id>/snapshots', methods=['POST'])
async def take_snapshot(request, machine_id):
    with data.Connection.use() as conn:

        snapshot_name = request.headers['json_params']['name']
        new_snapshot = data.Snapshot(machine=machine_id, name=snapshot_name)
        new_snapshot.save(conn=conn)

        new_request = data.Request(type=data.RequestType.TAKE_SNAPSHOT)
        new_request.machine = machine_id
        new_request.subject_id = new_snapshot.id
        new_request.save(conn=conn)

        # enqueue snapshot preparation
        data.Action(type='other', request=new_request.id).save(conn=conn)
        return sanic.response.json(
            {"responses": [{
                "type": "request_id",
                "request_id": new_request.id,
                "snapshot_id": new_snapshot.id,
                "is_last": True
            }]},
            status=200)


@snapshots.route('/machines/<machine_id>/snapshots/<snapshot_id>', methods=['PUT'])
async def restore_snapshot(request, machine_id, snapshot_id):
    with data.Connection.use() as conn:
        action = request.headers['json_params'].get('action')
        if action is None:
            raise InvalidUsage('\'action\' is missing in passed data!')
        elif action == 'restore':
            machine_ro = data.Machine.get_one({'_id': machine_id}, conn=conn)
            if snapshot_id not in machine_ro.snapshots:
                raise InvalidUsage(f'Machine \'{machine_id}\' does not have snapshot \'{snapshot_id}\'')
            new_request = data.Request(type=data.RequestType.RESTORE_SNAPSHOT)
            new_request.machine = machine_ro.id
            new_request.subject_id = snapshot_id
            new_request.save(conn=conn)

            # enqueue snapshot restoration
            data.Action(type='other', request=new_request.id).save(conn=conn)

            return sanic.response.json(
                {"responses": [{
                    "type": "request_id",
                    "request_id": new_request.id,
                    "is_last": True
                }]},
                status=200)

        else:
            raise InvalidUsage(f'Invalid \'action\' value: {action}')


@snapshots.route('/machines/<machine_id>/snapshots/<snapshot_id>', methods=['DELETE'])
async def delete_snapshot(request, machine_id, snapshot_id):
    with data.Connection.use() as conn:
        machine_ro = data.Machine.get_one({'_id': machine_id}, conn=conn)
        if snapshot_id not in machine_ro.snapshots:
            raise InvalidUsage(f'Machine \'{machine_id}\' does not have snapshot \'{snapshot_id}\'!')

        new_request = data.Request(type=data.RequestType.DELETE_SNAPSHOT)
        new_request.machine = machine_id
        new_request.subject_id = snapshot_id
        new_request.save(conn=conn)

        # enqueue snapshot deletion
        data.Action(type='other', request=new_request.id).save(conn=conn)

        return sanic.response.json(
            {"responses": [{
                "type": "request_id",
                "request_id": new_request.id,
                "is_last": True
            }]},
            status=200)
