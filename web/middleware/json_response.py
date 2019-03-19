import logging
import sys
import datetime
import json
from sanic.exceptions import abort
import sanic.exceptions
from sanic.response import json as sjson

logger = logging.getLogger()


async def output_dict(dictionary):
    if isinstance(dictionary, dict):
        if 'request_id' in dictionary:
            return {
                        **dictionary,
                        **{
                            'type': 'request_id'
                        }
                   }
        elif 'exception' in dictionary:
            return {
                        **dictionary,
                        **{
                            'type': 'exception',
                            'is_last': True
                        }
                   }
        else:
            return {
                        **dictionary,
                        **{
                            'type': 'return_value',
                            'response_id': 0
                        }
                   }
    return {}


async def json_response(request, response):
    result = []
    if isinstance(response, list):
        for item in response:
            result.append(await output_dict(item))
    elif isinstance(response, dict):
        result.append(await output_dict(response))
    else:
        return response

    return sjson(
                    {
                        'responses': result
                    },
                    status=200
    )
