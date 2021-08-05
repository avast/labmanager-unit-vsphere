import random
import logging
from sanic import request

logger = logging.getLogger(__name__)


def get_random_hash():
    hash = random.getrandbits(64)
    return "{0:016x}".format(hash)

def log_d(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.debug("{} {}".format(func_id, message))
    except:
        logger.debug(message)

def log_w(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.warn("{} {}".format(func_id, message))
    except:
        logger.warn(message)

def log_i(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.info("{} {}".format(func_id, message))
    except:
        logger.info(message)

def log_e(request, message):
    try:
        func_id = request.cookies["__log_extension"]
        logger.error("{} {}".format(func_id, message))
    except:
        logger.error(message)


def log_func_boundaries(func):
    async def inner(*args, **kwargs):
        function_name = func.__code__.co_name
        func_id = get_random_hash()
        logger.debug("func{}: {} started".format(func_id, function_name))
        if isinstance(args[0], request.Request):
            args[0].cookies.update({"__log_extension":"func{}:".format(func_id)})
        try:
            return await func.__call__(*args, **kwargs)
        except Exception as e:
            logger.debug("func{}: {} threw an exception: {}".format(func_id, function_name, e))
            raise
        finally:
            logger.debug("func{}: {} finished".format(func_id, function_name))

    return inner

