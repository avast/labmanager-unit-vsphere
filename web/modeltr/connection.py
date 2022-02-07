import psycopg2
from web.settings import Settings
import logging
import select

DEFAULT_CONNECTION_NAME = 'default'


class Connection(object):
    def __enter__(self):
        if self.async_mode:
            self.acursor.execute('BEGIN;')
            self.wait_for_completion()
        return self

    def __exit__(self, type, value, traceback):
        if traceback is None:
            if self.async_mode:
                self.acursor.execute('COMMIT;')
                self.wait_for_completion()
            else:
                self.client.commit()
        else:
            if self.async_mode:
                self.acursor.execute('ROLLBACK;')
                self.wait_for_completion()
            else:
                self.client.rollback()

            self.__logger.warning('Exception occurred when working with Connection, rolled back')

    def __init__(self, **kwargs):
        self.__logger = logging.getLogger(__name__)
        self.async_mode = False
        for i in range(Settings.app['retries']['db_connection']):
            try:
                self.async_mode = True if 'async_mode' in kwargs else False
                self.client = psycopg2.connect(kwargs['dsn'], async_=self.async_mode)
                if self.async_mode:
                    Connection.__wait_for_completion(self.client)
                    self.acursor = self.client.cursor()
                break
            except psycopg2.OperationalError:
                self.__logger.warning('Error connecting to the db server', exc_info=True)

    def get_cursor(self):
        return self.acursor if self.async_mode else self.client.cursor()

    def wait_for_completion(self):
        if self.async_mode:
            Connection.__wait_for_completion(client=self.client)

    __connections = {}

    @classmethod
    def connect(cls, alias=DEFAULT_CONNECTION_NAME, **kwargs):
        if alias not in cls.__connections:
            cls.__connections[alias] = {"connection": cls(**kwargs), "args": kwargs}
        return cls.use(alias)

    @classmethod
    def __wait_for_completion(cls, client):
        while client is not None:
            state = client.poll()
            if state == psycopg2.extensions.POLL_OK:
                break
            elif state == psycopg2.extensions.POLL_WRITE:
                select.select([], [client.fileno()], [])
            elif state == psycopg2.extensions.POLL_READ:
                select.select([client.fileno()], [], [])
            else:
                raise psycopg2.OperationalError(f'__wait_for_completion->poll() returned {state}')

    @classmethod
    def use(cls, alias=DEFAULT_CONNECTION_NAME):
        if alias not in cls.__connections:
            raise ValueError(f'connection {alias} has not been initialized before, please use connect method')

        connection = cls.__connections[alias]
        try:
            connection["connection"].client.reset()
        except (psycopg2.InterfaceError, psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            connection["connection"] = cls(**connection["args"])
        return cls.__connections[alias]["connection"]
