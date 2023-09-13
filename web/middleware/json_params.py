import logging
import json
from sanic.exceptions import abort

logger = logging.getLogger()


async def json_params(request):
    try:
        if request.headers.get('content-type', None) == 'application/json':
            if len(request.body) == 0:
                request.headers['json_params'] = {}
                return
            try:
                body_params = json.loads(request.body)
                request.headers['json_params'] = body_params
            except BaseException:
                abort('invalid params, input json cannot be parsed', 500)
    except BaseException as ex:
        logger.warning(f"Exception occurred when handling json params: {repr(ex)}", exc_info=True)