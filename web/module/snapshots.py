from sanic import Blueprint

snapshots = Blueprint('snapshots')


@snapshots.route('/machines/<machine_id>/snapshots', methods=['GET'])
async def machines_deploy(request, machine_id):
    return {'check': 'machines_get_snapshots {}, rq: {}'.format(machine_id, request.headers)}
