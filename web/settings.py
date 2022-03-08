import logging
import os
from collections import Iterable

import raven
import yaml
from deepmerge import Merger as dm


class Settings:
    app = {
            'unit_name': 'fake_unit',
            'log_level': 'DEBUG',
            'log_format': '%(asctime)s %(thread)d %(threadName)s %(levelname)s: %(message)s',
            'log_datefmt': '%Y-%m-%dT%H:%M:%S.000Z',
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
                'password': None
            },
            'vsphere': {
                'port': 443,
                'default_network_name': None,
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
                'clone_approach': 'linked_clone' # valid values: 'linked_clone', 'instant_clone'
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
                'load_refresh_interval': 5  # in number of deployed machines
            }
          }

    environ = os.environ.get('ENV', 'development')

    __config_file = os.environ.get('CONFIG', os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '../config/lm-unit.yaml'
    ))

    __config = yaml.safe_load(open(__config_file, 'r').read())

    raven = None

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


Settings.configure()
logging.basicConfig(
  level=getattr(logging, Settings.app['log_level']),
  format=Settings.app['log_format'],
  datefmt=Settings.app['log_datefmt']
)
