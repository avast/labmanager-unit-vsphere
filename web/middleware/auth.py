import logging
from sanic.exceptions import abort

logger = logging.getLogger()


async def auth(request):
    if 'authorization' not in request.headers:
        abort(401)

    request.headers['AUTHORISED_AS'] = 'user'
