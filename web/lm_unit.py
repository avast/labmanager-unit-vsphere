from sanic import Sanic
from sanic import response

import web.module.machines
import web.module.requests
import web.module.snapshots
import web.module.uptime
import web.middleware.auth
import web.middleware.json_params
import web.middleware.json_response


lm_unit_webserver = Sanic(__name__)

lm_unit_webserver.register_middleware(web.middleware.auth.auth, 'request')
lm_unit_webserver.register_middleware(web.middleware.json_params.json_params, 'request')

lm_unit_webserver.blueprint(web.module.machines.machines, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.requests.requests, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.snapshots.snapshots, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.uptime.uptime, url_prefix='/api/v4')
lm_unit_webserver.blueprint(web.module.uptime.uptime, url_prefix='/')

lm_unit_webserver.register_middleware(web.middleware.json_response.json_response, 'response')
