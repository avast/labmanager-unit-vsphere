#!/usr/bin/env python3

import logging
import threading

import web.lm_unit
import web.modeltr as data
import web.settings
from web.settings import Settings

if __name__ == '__main__':

    logger = logging.getLogger(__name__)

    @web.lm_unit.lm_unit_webserver.listener('before_server_start')
    def cnf(sanic, loop):
        logger.debug(f'before_start {sanic} {hex(id(loop))} {threading.current_thread().name}')

    data.Connection.connect(dsn=Settings.app['db']['dsn'], async_mode=True)

    host = Settings.app['service']['host']
    port = Settings.app['service']['port']
    workers = Settings.app['service']['workers']
    web.lm_unit.lm_unit_webserver.run(host=host, port=port, workers=workers)
