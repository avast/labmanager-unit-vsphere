from contextlib import contextmanager
import psycopg2
from web.settings import Settings as settings
import logging

DEFAULT_CONNECTION_NAME = 'default'


class Connection(object):
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if traceback is None:
            self.client.commit()
            pass
        else:
            self.client.rollback()
            self.__logger.warn('Exception occurred in Connection, all changes rolled back')

    def __init__(self, **kwargs):
        self.__logger = logging.getLogger(__name__)
        for i in range(settings.app['retries']['db_connection']):
            try:
                self.client = psycopg2.connect(kwargs['dsn'])
                break
            except psycopg2.OperationalError as e:
                self.__logger.warn('Error connecting to the db server', exc_info=True)
                pass

    __connections = {}

    @classmethod
    def connect(cls, alias=DEFAULT_CONNECTION_NAME, **kwargs):
        if alias not in cls.__connections:
            cls.__connections[alias] = {"connection": cls(**kwargs), "args": kwargs}
        return cls.use(alias)

    @classmethod
    def use(cls, alias=DEFAULT_CONNECTION_NAME):
        if alias not in cls.__connections:
            raise ValueError(
                'connection {} has not been initialized before, please use connect method'.format(
                    alias
                )
            )
        connection = cls.__connections[alias]
        try:
            connection["connection"].client.reset()
        except (psycopg2.InterfaceError, psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            connection["connection"] = cls(**connection["args"])
        return cls.__connections[alias]["connection"]
