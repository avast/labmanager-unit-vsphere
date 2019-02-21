#!/usr/bin/env python3

from web.settings import Settings as settings
import logging
import datetime
import threading
import re
import time
import os
import sys
import web.modeltr as data
import signal

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    global process_actions
    logger.info('worker aborted by signal: {}'.format(signum))
    process_actions = False


if __name__ == '__main__':

    data.Connection.connect(
                            'conn2',
                            dsn=settings.app['db']['dsn']
    )

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    process_actions = True
    while process_actions:
        with data.Connection.use('conn2') as conn:
            time.sleep(1.5)
            try:
                now = datetime.datetime.now()
                action = data.Action.get_one_for_update_skip_locked({'lock': 1}, conn=conn)
                if action and action.next_try < now:
                    if True:
                        if action.repetitions == 0:
                            logger.info('action {} timeouted'.format(action.id))
                            request = data.Request.get_one_for_update(
                                                                        {'_id': action.request},
                                                                        conn=conn
                            )
                            request.state = 'timeouted'
                            request.save(conn=conn)
                            action.lock = -1
                            action.save(conn=conn)
                        else:
                            logger.debug('firing action: {}'.format(action.id))
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
                settings.raven.captureException(exc_info=True)
                logger.error('Exception while processing request: ', exc_info=True)

    logger.debug("Delayed finished")
