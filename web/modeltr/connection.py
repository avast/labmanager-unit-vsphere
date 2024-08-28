import asyncio
import sys
import psycopg2
from web.settings import Settings
import logging
import select
import time

DEFAULT_CONNECTION_NAME = 'default'

class UnitDbConnectionError(Exception):
    pass

class Connection(object):
    def __enter__(self):
        if self._refresh_conn_on_every_usage():
            self._last_usage_timestamp = None
            self._connect()
            self.__logger.debug("db connection CONNECTED (on_every_usage)")
        if self.client is None:
            self._last_usage_timestamp = None
            self._connect()
            self.__logger.debug("db connection CONNECTED")
        if self.async_mode:
            try:
                self.acursor.execute('BEGIN;')
                self.wait_for_completion()
            except (
                    UnitDbConnectionError,
                    psycopg2.ProgrammingError,
                    psycopg2.InterfaceError,
                    psycopg2.OperationalError
            ):
                try:
                    self.__logger.warning(
                        'Connection to the db has failed, re-connecting...',
                        exc_info=True
                    )
                    self._connect()
                    self.acursor.execute('BEGIN;')
                    self.wait_for_completion()
                    self.__logger.warning('the db connection re-connected')
                except Exception:
                    self.__logger.warning(
                        'Connection to the db failed cannot be re-connected, '
                        'quitting the web server worker or service worker', exc_info=True
                    )
                    sys.exit(100)
            except BaseException as e:
                self.__logger.error(f"Connection->__enter__ unknown exception {type(e)} occurred", exc_info=True)
                raise e
        last_usage_gap = time.time() - self._last_usage_timestamp
        if (last_usage_gap > 30):
            self.__logger.info(f'Connection has not been used for {last_usage_gap} seconds')
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        try:
            if exc_traceback is None:
                if self.async_mode:
                    self.acursor.execute('COMMIT;')
                    self.wait_for_completion()
                else:
                    self.client.commit()
            else:
                self.__logger.warning(
                    f'Exception occurred when working with Connection, rolling back',
                    exc_info=(exc_type, exc_value, exc_traceback)
                )
                try:
                    if self.async_mode:
                        self.acursor.execute('ROLLBACK;')
                        self.wait_for_completion()
                    else:
                        self.client.rollback()

                    self.__logger.warning(
                        f'Exception occurred when working with Connection, rolled back'
                    )
                except Exception as ex:
                    self.__logger.warning(
                        f'Exception occurred when rolling back: {repr(ex)}'
                    )
        finally:
            self._last_usage_timestamp = time.time()
            try:
                if self._refresh_conn_on_every_usage():
                    self.client.close()
                    self.client = None
                    self.__logger.debug("db connection DIS-CONNECTED (on_every_usage)")
            except Exception as ex:
                self.__logger.warning("Connection autoclose has not been successful")

    def __init__(self, **kwargs):
        self.__logger = logging.getLogger(__name__)
        self.async_mode = False
        self._connection_params = kwargs
        self._last_usage_timestamp = None
        self.client = None
        #self._connect()

    def _connect(self):
        for i in range(Settings.app['retries']['db_connection']):
            try:
                self.async_mode = True if 'async_mode' in self._connection_params else False
                self.client = psycopg2.connect(self._connection_params['dsn'], async_=int(self.async_mode))
                if self.async_mode:
                    Connection.__wait_for_completion(self.client)
                    self.acursor = self.client.cursor()
                break
            except psycopg2.OperationalError:
                self.__logger.warning('Error connecting to the db server', exc_info=True)
                time.sleep(0.1)
        self._last_usage_timestamp = time.time()

    def _refresh_conn_on_every_usage(self):
        return "socket_reusability" in self._connection_params and \
            self._connection_params["socket_reusability"] == "never"

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
                cls.__poll_write_wait(client.fileno())
            elif state == psycopg2.extensions.POLL_READ:
                # select.select([client.fileno()], [], [])
                cls.__poll_read_wait(client.fileno())
            else:
                raise psycopg2.OperationalError(
                    f'__wait_for_completion->poll() returned {state}'
                )

    @classmethod
    def __poll_write_wait(cls, fileno):
        cnt = 0
        sleep_time = Settings.app['db']['async_polling']['sleep_time']
        while True:
            [_, write_fds, _] = select.select([], [fileno], [], 0.0)
            if write_fds == [fileno]:
                break
            time.sleep(sleep_time)
            cnt += 1
            elapsed_time = cnt * sleep_time
            if elapsed_time > Settings.app['db']['async_polling']['warning_time']:
                logging.getLogger(__name__).warning(
                    f'__poll_write_async_wait takes too long: now {int(elapsed_time)} secs in total'
                )
            if elapsed_time > Settings.app['db']['async_polling']['exception_time']:
                # this practically means that if the client cannot put any data within
                # exception_time seconds, we consider the connection as broken
                raise UnitDbConnectionError(f"did not obtain response within {elapsed_time} s")


    @classmethod
    def __poll_read_wait(cls, fileno):
        cnt = 0
        sleep_time = Settings.app['db']['async_polling']['sleep_time']
        while True:
            [read_fds, _, _] = select.select([fileno], [], [], 0.0)
            if read_fds == [fileno]:
                break
            time.sleep(sleep_time)
            cnt += 1
            elapsed_time = cnt * sleep_time
            if elapsed_time > Settings.app['db']['async_polling']['warning_time']:
                logging.getLogger(__name__).warning(
                    f'__poll_read_async_wait takes too long: now {int(elapsed_time)} secs in total'
                )
            if elapsed_time > Settings.app['db']['async_polling']['exception_time']:
                # this practically means that if the db server cannot send
                # any data within exception_time seconds, we consider the connection as broken
                raise UnitDbConnectionError(f"did not obtain response within {elapsed_time} s")

    @classmethod
    def use(cls, alias=DEFAULT_CONNECTION_NAME):
        if alias not in cls.__connections:
            raise ValueError(f'connection {alias} has not been initialized before, '
                             f'please use connect method')

        connection = cls.__connections[alias]
        try:
            if not connection["connection"].async_mode:
                try:
                    if connection["connection"].client:
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
