import logging
import sys
import datetime
import json
from sanic.exceptions import abort
import sanic.exceptions
from sanic.response import json as sjson

logger = logging.getLogger()


async def json_response(request, response):
    if isinstance(response, dict):
        return sjson(response)
