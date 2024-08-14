import logging
import functools
import os
from collections import Iterable

import raven
import yaml
from deepmerge import Merger as dm
import statsd
import contextvars


class Settings:
    app = {
            'unit_name': 'fake_unit',
            'log_level': 'DEBUG',
            'log_format': '[%(asctime)s] [%(process)d] [%(levelname)s] '
                          '[http:%(http_request_uuid)s] [%(http_verb)s%(http_address)s] '
                          '%(message)s',
            'log_datefmt': '%Y-%m-%dT%H:%M:%S.000Z',
            'sanic_accesslog': True,
            'sanic_keepalive': False,
            'sanic_debug': False,
            'labels': [],
            'slot_limit': 5,
            'nosid_prefix': None,
            'raven': {
                'dsn': 'fake:dsn@fakehost.com/fake'
            },
            'db': {
                'host': 'localhost',
                'ssl': False,
                'ssl_ca_certs_file': None,
                'username': None,
                'password': None,
                'socket_reusability': 'never'
            },
            'vsphere': {
                'port': 443,
                'default_network_name': None,
                'force_default_network_name': True,
                'templates': {
                    'skip_validation_for_suffix': None,
                },
                'retries': {
                    'deploy': 15,
                    'delete': 5,
                    'config_network': 6,
                    'default': 6,
                    'delay_period_min': 0,
                    'delay_period_max': 3
                },
                'datacenter': None,
                'root_system_folder': None,
                'instant_clone_enabled': False,
                'instant_clone_post_commands': [
                    {
                        'os': 'Win',
                        'description': 'restart network',
                        'command': 'schtasks.exe',
                        'args': '/run /tn restartnet'
                    }
                ],
                'timeout': 20,
                'hosts_folder_name': None,
                'hosts_shared_templates': True,
                'socket_default_timeout': None,
            },
            'vms': {
                'login_username': None,
                'login_password': None,
            },
            'service': {
                'listen': '127.0.0.1',
                'port': 8000,
                'personalised': False,
                'capabilities': {
                    # Each call to /capabilities induces 4 db requests
                    # If the unit fullness is under caching_enabled_threshold
                    # the db query is performed only once in the caching_period interval
                    'caching_period': 15,             # in seconds
                    'caching_enabled_threshold': 90,  # in percent
                },
                'screenshot_store': 'db',  # hcp eventually
            },
            'hcp': {
                'url': None,
                'auth': None,
                'base_dir': 'ss',
                'timeout': 120,
            },
            'retries': {
                'db_connection': 6,
                'default': 6,
                'delay_period_min': 0,
                'delay_period_max': 3
            },
            'worker': {
                'idle_counter': 60,
                'loop_initial_sleep': 0.5,
                'loop_idle_sleep': 1.5,
                'load_refresh_interval': 5,  # in number of deployed machines
                'getinfo_default_repetition_count': 20,
            },
            'statsd': {
                'host': 'foo.bar.com',
                'port': 0,
                'prefix': None
            },
            'delayed': {
                'sleep': 1.5,
            },
            'ticketeer': {
                'sleep': 6,
            },
            'document_abstraction':{
                'warn_0_records': True,
            }
          }

    environ = os.environ.get('ENV', 'development')

    __config_file = os.environ.get('CONFIG', os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '../config/lm-unit.yaml'
    ))

    __config = yaml.safe_load(open(__config_file, 'r').read())

    raven = None

    statsd_client = None

    @staticmethod
    def __flatten(items):
        """Yield items from any nested iterable; see Reference."""
        for item in items:
            if isinstance(item, Iterable) and not isinstance(item, (str, bytes)):
                for sub_x in Settings.__flatten(item):
                    yield sub_x
            else:
                yield item

    @staticmethod
    def configure():
        config_file_section = Settings.__config[Settings.environ]
        config_file_section['labels'] = \
            list(Settings.__flatten(config_file_section['labels']))
        dm(
            [(list, ['append']), (dict, ['merge'])],
            ['override'],
            ['override']
        ).merge(Settings.app, config_file_section)
        Settings.raven = raven.Client(
            dsn=Settings.app['raven']['dsn'],
            ignore_exceptions=[KeyboardInterrupt]
        )
        if Settings.app['statsd']['prefix']:
            try:
                Settings.statsd_client = statsd.StatsClient(
                    Settings.app['statsd']['host'],
                    Settings.app['statsd']['port']
                )
            except Exception as ex:
                logging.getLogger("settings").warning(
                    "Statsd client initialization failed, no stats gonna be sent",
                    exc_info=True
                )
                Settings.statsd_client = None


Settings.configure()

# Define a new log level More detailed than DEBUG
VERBOSE = 5
logging.addLevelName(VERBOSE, "VERBOSE")


# Add a method to log at the new level
def verbose(self, message, *args, **kwargs):
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs)


logging.Logger.verbose = verbose

log_level_str = Settings.app['log_level']
env_log_level_str = os.environ.get("SANICAPP_WORKERS_LOG_LEVEL", "None")
if env_log_level_str in ['VERBOSE', 'DEBUG', 'INFO', 'WARNING']:
    log_level_str = env_log_level_str


logging_vars = {
    'http_request_uuid': contextvars.ContextVar('http_request_uuid', default=''),
    'http_verb': contextvars.ContextVar('http_verb', default=''),
    'http_address': contextvars.ContextVar('http_address', default=''),
}


def set_context_var(name, val):
    logging_vars[name].set(val)


def reset_context_var(name):
    logging_vars[name].set('')


logging.basicConfig(
  level=getattr(logging, log_level_str),
  format=Settings.app['log_format'],
  datefmt=Settings.app['log_datefmt']
)


old_factory = logging.getLogRecordFactory()
def record_factory(*args, **kwargs):
    record = old_factory(*args, **kwargs)
    record.http_request_uuid = logging_vars['http_request_uuid'].get()
    record.http_verb = logging_vars['http_verb'].get()
    record.http_address = logging_vars['http_address'].get()
    return record
logging.setLogRecordFactory(record_factory)


def log_to(logger: logging.Logger, level=logging.DEBUG):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.log(level=level, msg=f"-> {func.__name__}()")
            result = func(*args, **kwargs)
            logger.log(level=level, msg=f"<- {func.__name__}(): {repr(result)}")
            return result
        return wrapper
    return decorator
