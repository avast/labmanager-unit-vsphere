from pymongo import MongoClient
from contextlib import contextmanager
import logging

DEFAULT_CONNECTION_NAME = 'default'


class Connection(object):
    def __enter__(self):
        self.session = self.client.start_session()
        return self

    def __exit__(self, type, value, traceback):
        if traceback is None:
            self.__logger.debug('Connection successful')
        else:
            self.__logger.debug('Exception occurred in Connection')

        self.session.end_session()

    # example usage: web.modeltr.connection.Connection(
    #   host='localhost', authSource='test_database', replicaSet='rs0')
    # auth source must be present here
    def __init__(self, **kwargs):
        self.__logger = logging.getLogger(__name__)
        self.client = MongoClient(**kwargs)
        self.database = kwargs['authSource']

    __connections = {}

    @classmethod
    def connect(cls, alias=DEFAULT_CONNECTION_NAME, **kwargs):
        if alias not in cls.__connections:
            cls.__connections[alias] = cls(**kwargs)
        return cls.use(alias)

    @classmethod
    def use(cls, alias=DEFAULT_CONNECTION_NAME):
        if alias not in cls.__connections:
            raise ValueError(
                'connection {} has not been initialized before, please use connect method'.format(
                    alias
                )
            )
        return cls.__connections[alias]


class Transaction(object):
    def __enter__(self):
        self.transaction = self.conn.session.start_transaction()
        return self

    def __exit__(self, type, value, traceback):
        if traceback is None:
            self.__logger.debug('Transaction successful')
            self.conn.session.commit_transaction()
            self.__logger.debug('Transaction has been committed successfully')
        else:
            self.conn.session.abort_transaction()
            self.__logger.debug('Exception occurred during transaction')

    def __init__(self, connection):
        self.conn = connection
        self.__logger = logging.getLogger(__name__)
