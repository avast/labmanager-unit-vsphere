import logging
import yaml
from deepmerge import Merger as dm
import os


class Settings:
    app = {
            'unit_name': 'fake_unit',
            'log_level': 'DEBUG',
            'db': {
                'host': 'localhost'
            },
            'vsphere': {
                'port': 443
            },
            'service': {
                'listen': '127.0.0.1',
                'port': 8000
            }
          }

    environ = os.environ.get('ENV', 'development')

    __config_file = os.environ.get('CONFIG', os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '../config/lm-unit.yaml'
    ))

    __config = yaml.safe_load(open(__config_file, 'r').read())

    def configure():
        dm(
            [(list, ['append']), (dict, ['merge'])],
            ['override'],
            ['override']
        ).merge(Settings.app, Settings.__config[Settings.environ])


Settings.configure()
logging.basicConfig(level=getattr(logging, Settings.app['log_level']))
