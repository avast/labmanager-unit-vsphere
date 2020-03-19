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


def get_struct(action, request, machine):
    return {
        "action": action,
        "request": request,
        "machine": machine,
        "transformations": [],
    }

def assign(a, b):
    a=b

def make_transformations(struct, conn):
    action = data.Action.get_one_for_update({'_id':struct['action'].id}, conn=conn)
    request = data.Request.get_one_for_update({'_id':action.request}, conn=conn)
    machine = data.Machine.get_one_for_update({'_id':request.machine}, conn=conn)

    for tr in struct["transformations"]:
        tr(action, request, machine)
        action.save(conn=conn)
        request.save(conn=conn)
        machine.save(conn=conn)

def process_actions_1(struct):
    a = 10
    struct["transformations"].append(lambda action, request, machine: setattr(action, "repetitions", a))
    struct["transformations"].append(lambda action, request, machine: machine.snapshots.append(1))
    return struct

def process_actions_2(struct):
    a = "jakejsi_cosi_foobar"
    struct["transformations"].append(lambda action, request, machine: setattr(request, "state", a))
    struct["transformations"].append(lambda action, request, machine: machine.snapshots.remove(1))
    return struct

def process_action(action_id):
    action_ro = None
    request_ro = None
    machine_ro = None
    with data.Connection.use('conn2') as conn:
        action_ro = data.Action.get_one({'_id':action_id}, conn=conn)
        request_ro = data.Request.get_one({'_id':action_ro.request}, conn=conn)
        machine_ro = data.Action.get_one({'_id':request_ro.machine}, conn=conn)

    struct = get_struct(action_ro, request_ro, machine_ro)
    struct = process_actions_1(struct)
    struct = process_actions_2(struct)


    with data.Connection.use('conn2') as conn:
        make_transformations(struct, conn)


if __name__ == '__main__':

    data.Connection.connect(
                            'conn2',
                            dsn=settings.app['db']['dsn']
    )

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    process_actions = True
    while process_actions:
        action_id = None
        with data.Connection.use('conn2') as conn:
            time.sleep(1.5)
            try:
                now = datetime.datetime.now()
                action = data.Action.get_one({'_id':10679}, conn=conn)
                action_id = action.id
                print(action_id)
            except Exception:
                settings.raven.captureException(exc_info=True)
                logger.error('Exception while processing request: ', exc_info=True)
        process_action(action_id)
        break;

    logger.debug("Delayed finished")
