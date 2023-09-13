#!/usr/bin/env python3

import web.lm_unit
import web.settings
from web.settings import Settings

if __name__ == '__main__':
    host = Settings.app['service']['host']
    port = Settings.app['service']['port']
    workers = Settings.app['service']['workers']
    log = Settings.app['sanic_accesslog']
    debug = Settings.app['sanic_debug']
    web.lm_unit.lm_unit_webserver.run(host=host, port=port, workers=workers, access_log=log, debug=debug)

