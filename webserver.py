#!/usr/bin/env python3

from web.settings import Settings as settings
import logging

import web.lm_unit
import web.modeltr as data
import web.settings
import threading


if __name__ == '__main__':

    logger = logging.getLogger(__name__)

    @web.lm_unit.lm_unit_webserver.listener('before_server_start')
    def cnf(sanic, loop):
        logger.debug('before_start {} {} {}'.format(
                                                    sanic,
                                                    hex(id(loop)),
                                                    threading.current_thread().name
        ))
    data.Connection.connect(
                            dsn=settings.app['db']['dsn']
    )

    web.lm_unit.lm_unit_webserver.run(
                                        host=settings.app['service']['host'],
                                        port=settings.app['service']['port'],
                                        workers=settings.app['service']['workers']
    )
