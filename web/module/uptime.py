import datetime
from sanic import Blueprint
import sanic.response
import socket

uptime = Blueprint('uptime')


@uptime.route('/uptime')
async def uptime(request):
    return sanic.response.json({
        'current_time': datetime.datetime.now().strftime("%Y-%m-%d, %H:%M:%S"),
        'timezone': str(datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo),
        'host': socket.gethostname(),
    }, status=200)
