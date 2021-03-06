from web.settings import Settings as settings
from sanic import Sanic
from sanic import response
from sanic.handlers import ErrorHandler
import logging
import web.module.machines
import web.module.requests
import web.module.capabilities
import web.module.snapshots
import web.module.screenshots
import web.module.uptime

import web.middleware.auth
import web.middleware.auth_ldap
import web.middleware.auth_merger
import web.middleware.json_params
import web.middleware.json_response

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


# lm_unit_webserver = Sanic(__name__, error_handler=LMUErrorHandler())
lm_unit_webserver = Sanic(__name__)

if (settings.app['service'].get("auth_module", "<none>") == 'ldap_auth'):
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

lm_unit_webserver.register_middleware(web.middleware.json_response.json_response, 'response')
