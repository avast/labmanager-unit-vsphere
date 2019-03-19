import logging
import sys
import datetime
import json
from sanic.exceptions import abort
import sanic.exceptions

logger = logging.getLogger()


async def json_params(request):
    logger.debug(request.headers)
    logger.debug(request.body)
    if (request.headers.get('content-type', None) == 'application/json'):
        if len(request.body) == 0:
            request.headers['json_params'] = {}
            return
        try:
            body_params = json.loads(request.body)
            request.headers['json_params'] = body_params
        except BaseException:
            abort('invalid params, input json cannot be parsed', 500)
