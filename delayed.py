#!/usr/bin/env python3

import datetime
import logging
import signal
import time

import web.modeltr as data
from web.modeltr.enums import RequestState
from web.settings import Settings

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    global process_actions
    logger.info(f'worker aborted by signal: {signum}')
    process_actions = False


if __name__ == '__main__':

    data.Connection.connect('conn2', dsn=Settings.app['db']['dsn'])

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    process_actions = True
    while process_actions:
        with data.Connection.use('conn2') as conn:
            time.sleep(Settings.app['delayed']['sleep'])
            try:
                now = datetime.datetime.now()
                action = data.Action.get_one_for_update_skip_locked({'lock': 1}, conn=conn)

                if action and action.next_try < now:
                    if action.repetitions == 0:
                        logger.info(f'action {action.id} timeouted')
                        request = data.Request.get_one_for_update(
                                                                    {'_id': action.request},
                                                                    conn=conn
                        )
                        request.state = RequestState.TIMEOUTED
                        request.save(conn=conn)
                        action.lock = -1
                        action.save(conn=conn)
                    else:
                        logger.debug(f'firing action: {action.id}')
                        logger.debug(action.to_dict())
                        action.lock = 0
                        action.next_try = datetime.datetime(
                                                            year=datetime.MAXYEAR,
                                                            month=1,
                                                            day=1
                        )
                        action.save(conn=conn)
                        logger.debug('firing done: {}'.format(action.id))

            except Exception:
                Settings.raven.captureException(exc_info=True)
                logger.error('Exception while processing request: ', exc_info=True)

    logger.debug("Delayed finished")
