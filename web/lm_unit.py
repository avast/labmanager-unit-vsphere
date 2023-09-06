import asyncio
import logging

from sanic import Sanic
from sanic import response
from sanic.handlers import ErrorHandler

import web.middleware.auth
import web.middleware.auth_ldap
import web.middleware.auth_merger
import web.middleware.json_params
import web.middleware.json_response
import web.module.capabilities
import web.module.machines
import web.module.requests
import web.module.screenshots
import web.module.snapshots
import web.module.uptime
import web.module.hosts
from web.settings import Settings as settings
import web.modeltr as data

logger = logging.getLogger()


class LMUErrorHandler(ErrorHandler):
    def default(self, request, exception):
        return response.json(
            {
                'responses': [
                    {
                        'type': 'exception',
                        'response_id': 0,
                        'exception': str(type(exception).__name__),
                        'exception_args': exception.args,
                        'exception_traceback': str(exception.__traceback__),
                        'is_last': True
                    }
                ]
            },
            status=500
        )


lm_unit_webserver = Sanic(__name__)

if settings.app['service'].get("auth_module", "<none>") == 'ldap_auth':
    logger.debug("Registering ldap_auth....")
    lm_unit_webserver.register_middleware(web.middleware.auth_ldap.auth, 'request')
    logger.debug("Registered ldap_auth sucessfully")
else:
    lm_unit_webserver.register_middleware(web.middleware.auth.auth, 'request')
lm_unit_webserver.register_middleware(web.middleware.auth_merger.auth, 'request')

lm_unit_webserver.register_middleware(web.middleware.json_params.json_params, 'request')

lm_unit_webserver.blueprint(web.module.machines.machines, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.requests.requests, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.snapshots.snapshots, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.screenshots.screenshots, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.uptime.uptime, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.capabilities.capabilities, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.uptime.uptime, url_prefix='/')
lm_unit_webserver.blueprint(web.module.hosts.hosts, url_prefix='/api/v4')

lm_unit_webserver.register_middleware(web.middleware.json_response.json_response, 'response')

@lm_unit_webserver.listener("before_server_start")
async def create_db_connection(app, loop):
    logger.debug(f"before_server_start {asyncio.current_task()}")
    data.Connection.connect(dsn=settings.app['db']['dsn'], async_mode=True)
