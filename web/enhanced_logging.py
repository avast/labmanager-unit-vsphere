import random
import logging
from sanic import request

logger = logging.getLogger(__name__)


def get_random_hash():
    hash = random.getrandbits(32)
    return "{0:08x}".format(hash)


def log_d(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.debug(f'{func_id} {message}')
    except:
        logger.debug(message)


def log_w(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.warning(f'{func_id} {message}')
    except:
        logger.warning(message)


def log_i(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.info(f'{func_id} {message}')
    except:
        logger.info(message)


def log_e(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.error(f'{func_id} {message}')
    except:
        logger.error(message)


def log_func_boundaries(func):
    async def inner(*args, **kwargs):
        function_name = func.__code__.co_name
        func_id = get_random_hash()
        logger.debug(f'func_{func_id}: {function_name} started')
        if isinstance(args[0], request.Request):
            # TODO: is colon ok here?
            args[0].cookies.update({'__log_extension': f'func_{func_id}:'})
        try:
            return await func.__call__(*args, **kwargs)
        except Exception as e:
            logger.debug(f'func_{func_id}: {function_name} threw an exception: {e}')
            raise
        finally:
            logger.debug(f'func_{func_id}: {function_name} finished')

    return inner
