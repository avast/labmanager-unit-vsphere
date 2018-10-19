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


logger = logging.getLogger(__name__)

if __name__ == '__main__':

    data.Connection.connect(
                            'conn2',
                            host=settings.app['db']['host'],
                            authSource=settings.app['db']['database'],
                            replicaSet=settings.app['db']['replica_set']
    )

    idle_counter = 0
    with data.Connection.use('conn2') as conn:
        while True:
            try:
                now = datetime.datetime.now()
                actions = data.Action.get({'lock': 1}, conn=conn)
                for action in actions:
                    if action.next_try < now:
                        if action.repetitions == 0:
                            logger.info('action {} timeouted'.format(action.id))
                            request = data.Request.get({'_id': action.request}, conn=conn).first()
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
                logger.error('Exception while processing request: ', exc_info=True)

            time.sleep(5)
