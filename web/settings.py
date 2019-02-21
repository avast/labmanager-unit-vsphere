import logging
import yaml
from deepmerge import Merger as dm
import os
import raven


class Settings:
    app = {
            'unit_name': 'fake_unit',
            'log_level': 'DEBUG',
            'log_format': '%(asctime)s %(thread)d %(threadName)s %(levelname)s: %(message)s',
            'log_datefmt': '%Y-%m-%dT%H:%M:%S.000Z',

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
                'retries': {
                    'deploy': 15,
                    'delete': 5,
                    'config_network': 6,
                    'default': 6,
                    'delay_period_min': 0,
                    'delay_period_max': 3
                }
            },
            'service': {
                'listen': '127.0.0.1',
                'port': 8000
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
                'loop_idle_sleep': 1.5
            }
          }

    environ = os.environ.get('ENV', 'development')

    __config_file = os.environ.get('CONFIG', os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '../config/lm-unit.yaml'
    ))

    __config = yaml.safe_load(open(__config_file, 'r').read())

    raven = None

    def configure():
        dm(
            [(list, ['append']), (dict, ['merge'])],
            ['override'],
            ['override']
        ).merge(Settings.app, Settings.__config[Settings.environ])
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
