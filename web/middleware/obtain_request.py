import logging
import sys
import datetime
from sanic.exceptions import abort

logger = logging.getLogger()


async def obtain_request(request):
    logger.debug('request obtained {}'.format(request))
