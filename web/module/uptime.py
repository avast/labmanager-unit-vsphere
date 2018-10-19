from sanic import Blueprint
import datetime

uptime = Blueprint('uptime')


def uptime2():
    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.readline().split()[0])
    return uptime_seconds


@uptime.route('/uptime')
async def uptime_(request):
    return {
        'uptime': uptime2(),
        'current': datetime.datetime.now()
    }
