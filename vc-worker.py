#!/usr/bin/env python3

from web.settings import Settings as settings
import logging

import datetime
import random

import threading
import re
import time
import os
import sys
import web.modeltr as data
import vcenter.vcenter as vcenter


logger = logging.getLogger(__name__)


def get_template(labels):
    for l in labels:
        matches = re.match('template:(.*)', l)
        if (matches):
            return matches[1]
    raise ValueError('cannot get template name from labels')


def get_network_interface(labels):
    for l in labels:
        matches = re.match('config:network_interface=(.*)', l)
        if matches:
            return matches[1]
    return None


def get_inventory_folder(labels):
    for l in labels:
        matches = re.match('config:inventory_path=(.*)', l)
        if matches:
            return matches[1]
    return None


def action_deploy(conn, action, vc):
    logger = logging.getLogger('action_deploy')
    logger.info('{}-{}->'.format(os.getpid(), action.id))
    try:
        with data.Transaction(conn):
            request = data.Request.get({'_id': action.request}, conn=conn).first()
            machine = data.Machine.get({'_id': request.machine}, conn=conn).first()

            template = get_template(machine.labels)
            network_interface = get_network_interface(machine.labels)
            inventory_folder = get_inventory_folder(machine.labels)

            try:
                uuid = vc.deploy(
                                    template,
                                    '{}-{}'.format(template, request.machine),
                                    inventory_folder=inventory_folder
                                )
                if network_interface:
                    vc.config_network(uuid, interface_name=network_interface)
            except Exception:
                logger.info('Exception deploying machine: ', exc_info=True)

            machine.provider_id = uuid
            request.state = 'success'
            request.save(conn=conn)
            machine.state = 'deployed'
            machine.save(conn=conn)
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)
    except Exception:
        logger.error('Exception: ', exc_info=True)
    finally:
        logger.info('{}-{}<-'.format(os.getpid(), action.id))


def action_undeploy(conn, request, machine, vc):
    vc.stop(machine.provider_id)
    vc.undeploy(machine.provider_id)
    machine.state = 'undeployed'


def action_start(conn, request, machine, vc):
    vc.start(machine.provider_id)
    machine.state = 'running'


def action_stop(conn, request, machine, vc):
    vc.stop(machine.provider_id)
    machine.state = 'stopped'


def action_others(conn, action, vc):
    logger = logging.getLogger('action_others')

    logger.info('{}-{}->'.format(os.getpid(), action.id))
    request_type = data.Request.get({'_id': action.request}, conn=conn).first().type
    if request_type == 'get_info':
        with data.Transaction(conn):
            request = data.Request.get({'_id': action.request}, conn=conn).first()
            logger.debug(request.to_dict())
            machine = data.Machine.get({'_id': request.machine}, conn=conn).first()
            try:
                info = vc.get_machine_info(machine.provider_id)
                logger.debug(info)
            except Exception:
                logger.error('get_info exception: ', exc_info=True)
                info = {'ip_addresses': []}

            if len(info['ip_addresses']) != 0:
                machine.ip_addresses = info['ip_addresses']
                machine.save(conn=conn)
                request.state = 'success'
                action.lock = -1
            else:
                request.state = 'delayed'
                action.repetitions -= 1
                action.next_try = datetime.datetime.now() + datetime.timedelta(
                    seconds=random.randint(action.delay, action.delay+3)
                )
                action.lock = 1
            request.save(conn=conn)
        action.save(conn=conn)
        logger.info('{}-{}<-'.format(os.getpid(), action.id))
        return

    try:
        with data.Transaction(conn):
            request = data.Request.get({'_id': action.request}, conn=conn).first()
            machine = data.Machine.get({'_id': request.machine}, conn=conn).first()
            logger.info('{}-{}->{}'.format(os.getpid(), action.id, request.type))
            if request_type == 'undeploy':
                action_undeploy(conn, request, machine, vc)
            elif request_type == 'start':
                action_start(conn, request, machine, vc)
            elif request_type == 'stop':
                action_stop(conn, request, machine, vc)
            else:
                logger.warn('unknown request: {} is going to succeed'.format(request.type))
            request.state = 'success'
            request.save(conn=conn)
            machine.save(conn=conn)
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)

        if request_type == 'start':
            # create another task to get info about that machine
            with data.Transaction(conn):
                machine = data.Machine.get({'_id': request.machine}, conn=conn).first()
                new_request = data.Request(type='get_info', machine=str(machine.id))
                new_request.save(conn=conn)
                machine.requests.append(new_request.id)
                machine.save(conn=conn)
                data.Action(
                    type='other',
                    request=new_request.id,
                    repetitions=20,
                    delay=10
                ).save(conn=conn)

    except Exception:
        logger.error('Exception: ', exc_info=True)

    finally:
        logger.info('{}-{}<-'.format(os.getpid(), action.id))


if __name__ == '__main__':

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = 'other'

    data.Connection.connect(
                            'conn1',
                            host=settings.app['db']['host'],
                            authSource=settings.app['db']['database'],
                            replicaSet=settings.app['db']['replica_set'],
                            ssl=settings.app['db']['ssl'],
                            ssl_ca_certs=settings.app['db']['ssl_ca_certs_file'],
                            username=settings.app['db']['username'],
                            password=settings.app['db']['password']
    )
    vc = vcenter.VCenter()
    vc.connect()

    idle_counter = 0
    with data.Connection.use('conn1') as conn:
        while True:
            try:
                action = data.Action.get_eldest_excl({'type': mode, 'lock': 0}, conn=conn)
                if action:
                    if mode == 'deploy':
                        action_deploy(conn, action, vc)
                    else:
                        action_others(conn, action, vc)
                else:
                    idle_counter += 1
                    if idle_counter > 20:
                        vc.idle()
                        idle_counter = 0
                    time.sleep(5)
            except Exception:
                logger.error('Exception while processing request: ', exc_info=True)
