import logging
import sys
import datetime
import json
from sanic.exceptions import abort
import sanic.exceptions

logger = logging.getLogger()


async def json_params(request):
    if (request.headers.get('content-type', None) == 'application/json'):
        try:
            body_params = json.loads(request.body)
            request.headers['json_params'] = body_params
        except BaseException:
            raise sanic.exceptions.InvalidUsage(
                json.dumps({'error': 'malformatted input json data'})
            )
