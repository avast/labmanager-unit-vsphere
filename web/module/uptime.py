import datetime
import sanic.response
from sanic import Blueprint
import socket
from web.modeltr import Connection
import web.modeltr.document
uptime = Blueprint('uptime')


@uptime.route('/uptime')
async def uptime_func(request):
    return sanic.response.json({
        'current_time': datetime.datetime.now().strftime("%Y-%m-%d, %H:%M:%S"),
        'timezone': str(datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo),
        'host': socket.gethostname(),
    }, status=200)


async def check_db():
    with Connection.use() as conn:
        return web.modeltr.document.Document.test_db_connection(conn=conn)


@uptime.route('/dbuptime')
async def dbuptime_func(request):
    return sanic.response.json({
        'current_time': datetime.datetime.now().strftime("%Y-%m-%d, %H:%M:%S"),
        'timezone': str(datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo),
        'host': socket.gethostname(),
        'db': await check_db(),
    }, status=200)
