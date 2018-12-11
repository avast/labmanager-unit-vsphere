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
                                host=settings.app['db']['host'],
                                authSource=settings.app['db']['database'],
                                replicaSet=settings.app['db']['replica_set'],
                                ssl=settings.app['db']['ssl'],
                                ssl_ca_certs=settings.app['db']['ssl_ca_certs_file'],
                                username=settings.app['db']['username'],
                                password=settings.app['db']['password']
        )

    web.lm_unit.lm_unit_webserver.run(
                                        host=settings.app['service']['host'],
                                        port=settings.app['service']['port'],
                                        workers=settings.app['service']['workers']
    )
