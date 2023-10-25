import asyncio

import psycopg2
from web.settings import Settings
import logging
import select
import time

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
                self.client = psycopg2.connect(kwargs['dsn'], async_=int(self.async_mode))
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
                # select.select([], [client.fileno()], [])
                cls.__poll_write_async_wait(client.fileno())
            elif state == psycopg2.extensions.POLL_READ:
                # select.select([client.fileno()], [], [])
                cls.__poll_read_async_wait(client.fileno())
            else:
                raise psycopg2.OperationalError(
                    f'__wait_for_completion->poll() returned {state}'
                )

    @classmethod
    def __poll_write_async_wait(cls, fileno):
        cnt = 0
        while True:
            [_, write_fds, _] = select.select([], [fileno], [], 0.0)
            if write_fds == [fileno]:
                break
            time.sleep(0.1)
            cnt += 1
            if cnt > 10:
                logging.getLogger(__name__).warning(f'__poll_write_async_wait takes too long:')


    @classmethod
    def __poll_read_async_wait(cls, fileno):
        cnt = 0
        sleep_time = 0.2
        while True:
            [read_fds, _, _] = select.select([fileno], [], [], 0.0)
            if read_fds == [fileno]:
                break
            time.sleep(sleep_time)
            cnt += 1
            if cnt > 15:
                logging.getLogger(__name__).warning(
                    f'__poll_read_async_wait takes too long: now {cnt*sleep_time} secs in total'
                )

    @classmethod
    def use(cls, alias=DEFAULT_CONNECTION_NAME):
        if alias not in cls.__connections:
            raise ValueError(f'connection {alias} has not been initialized before, '
                             f'please use connect method')

        connection = cls.__connections[alias]
        try:
            if not connection["connection"].async_mode:
                try:
                    connection["connection"].client.reset()
                except (psycopg2.InterfaceError,
                        psycopg2.OperationalError,
                        psycopg2.DatabaseError,
                        psycopg2.ProgrammingError
                ) as e:
                    logging.getLogger(__name__).error(
                        f'Exception occurred when resetting the Connection: {repr(e)}',
                        exc_info=True
                    )
                    connection["connection"] = cls(**connection["args"])
        except Exception as ex:
            logging.getLogger(__name__).error(
                f'Exception when calling use(): {repr(ex)}', exc_info=True
            )
        return connection["connection"]
