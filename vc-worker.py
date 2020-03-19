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
import signal

from web.modeltr.machine import MachineState

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


def process_deploy_action(conn, action, vc):
    logger = logging.getLogger('action_deploy')
    try:
        request = data.Request.get_one_for_update({'_id': action.request}, conn=conn)
        machine_ro = data.Machine.get_one({'_id': request.machine}, conn=conn)
        logger.info('{}-{}->deploy|machine.state: {}'.format(
                                                                os.getpid(),
                                                                action.id,
                                                                machine_ro.state
        )
        )

        template = get_template(machine_ro.labels)

        if settings.app['vsphere']['default_network_name']:
            network_interface = settings.app['vsphere']['default_network_name']
        else:
            network_interface = get_network_interface(machine_ro.labels)

        inventory_folder = get_inventory_folder(machine_ro.labels)
        machine_info = {'nos_id': ''}
        if settings.app['unit_name']:
            output_machine_name = '{}-{}-{}'.format(
                template,
                settings.app['unit_name'],
                request.machine
            )
        else:
            output_machine_name = '{}-{}'.format(template, request.machine)

        try:
            uuid = vc.deploy(
                                template,
                                output_machine_name,
                                inventory_folder=inventory_folder
                            )
            if network_interface:
                vc.config_network(uuid, interface_name=network_interface)
            machine_info = vc.get_machine_info(uuid)
        except Exception as e:
            settings.raven.captureException(exc_info=True)
            logger.info('Exception deploying machine: ', exc_info=True)
            raise e
        if machine_info['nos_id'] == '' or machine_info['nos_id'] is None:
            vc.stop(uuid)
            vc.undeploy(uuid)
            raise "NOS id hasn't been returned for machine {}" + \
                ", it is essential to be obtained".format(uuid)

        machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
        machine.provider_id = uuid
        machine.nos_id = machine_info['nos_id']
        machine.machine_name = machine_info['machine_name']
        machine.machine_search_link = machine_info['machine_search_link']
        request.state = 'success'
        request.save(conn=conn)
        machine.state = MachineState.DEPLOYED.value
        machine.save(conn=conn)
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)
    except Exception:
        settings.raven.captureException(exc_info=True)
        logger.error('action_deploy exception: ', exc_info=True)

        request.state = 'failed'
        request.save(conn=conn)
        machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
        machine.state = MachineState.FAILED.value
        machine.save(conn=conn)
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)
    finally:
        logger.info('{}-{}<-'.format(os.getpid(), action.id))


def action_undeploy(request, machine, vc):
    vc.stop(machine.provider_id)
    vc.undeploy(machine.provider_id)
    return MachineState.UNDEPLOYED


def action_start(request, machine, vc):
    vc.start(machine.provider_id)
    return MachineState.RUNNING


def action_stop(request, machine, vc):
    vc.stop(machine.provider_id)
    return MachineState.STOPPED


def action_get_info(request, machine_ro, vc, action, conn):
    logger.debug(request.to_dict())
    try:
        info = vc.get_machine_info(machine_ro.provider_id)
        logger.debug(info)
    except Exception:
        logger.error('get_info exception: ', exc_info=True)
        info = {'ip_addresses': [], 'nos_id': '', 'machine_search_link': ''}

    machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
    machine.nos_id = info['nos_id']
    machine.machine_search_link = info['machine_search_link']

    if len(info['ip_addresses']) != 0:
        machine.ip_addresses = info['ip_addresses']
        machine.save(conn=conn)
        request.state = 'success'
        action.lock = -1
    else:
        machine.save(conn=conn)
        request.state = 'delayed'
        action.repetitions -= 1
        action.next_try = datetime.datetime.now() + datetime.timedelta(
            seconds=random.randint(action.delay, action.delay+3)
        )
        action.lock = 1
    request.save(conn=conn)
    action.save(conn=conn)


def enqueue_get_info_request(request, machine, conn):
    # create another task to get info about that machine
    logger.debug('creating another get_info action for {}'.format(request.machine))
    new_request = data.Request(type='get_info', machine=str(machine.id))
    new_request.save(conn=conn)
    machine.requests.append(new_request.id)
    machine.save(conn=conn)
    data.Action(
            type='other',
            request=new_request.id,
            repetitions=20,
            delay=10,
            next_try=datetime.datetime.now() + datetime.timedelta(seconds=5)
    ).save(conn=conn)


def action_take_screenshot(request, machine, vc, conn):
    screenshot_data = vc.take_screenshot(machine.provider_id)
    if request.subject_id:
        ss = data.Screenshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        if screenshot_data:
            ss.image_base64 = screenshot_data.decode("utf-8")
            ss.status = "obtained"
        else:
            ss.image_base64 = ""
            ss.status = "error"
        ss.save(conn=conn)
    else:
        settings.raven.captureMessage('Error obtaining subject_id from Request')
    return None


def action_take_snapshot(request, machine, vc, conn):
    if request.subject_id:
        snap_ro = data.Snapshot.get_one({'_id': request.subject_id}, conn=conn)
        result = vc.take_snapshot(uuid=machine.provider_id, snapshot_name=snap_ro.get_uniq_name())
        snap = data.Snapshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        snap.status = 'success' if result is True else 'failed'
        snap.save(conn=conn)
        if result is True:
            # attach snapshot from machine if creating was successful
            machine = data.Machine.get_one_for_update({'_id': machine.id}, conn=conn)
            machine.snapshots.append(snap.id)
            machine.save(conn=conn)

    else:
        settings.raven.captureMessage('Error obtaining subject_id for take snapshot request')
    return None


# TODO deduplicate with 'action_take_snapshot()' later
def action_restore_snapshot(request, machine, vc, conn):
    if request.subject_id:
        snap_ro = data.Snapshot.get_one({'_id': request.subject_id}, conn=conn)
        result = vc.revert_snapshot(uuid=machine.provider_id, snapshot_name=snap_ro.get_uniq_name())
        snap = data.Snapshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        snap.status = 'success' if result is True else 'failed'
        snap.save(conn=conn)
    else:
        settings.raven.captureMessage('Error obtaining subject_id for restore snapshot request')

    return None


# TODO deduplicate with 'action_take_snapshot()' later
def action_delete_snapshot(request, machine, vc, conn):
    if request.subject_id:
        snap_ro = data.Snapshot.get_one({'_id': request.subject_id}, conn=conn)
        result = vc.remove_snapshot(uuid=machine.provider_id, snapshot_name=snap_ro.get_uniq_name())
        snap = data.Snapshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        snap.status = 'success' if result is True else 'failed'
        snap.save(conn=conn)
        if result is True:
            # detach snapshot from machine if remove was successful
            machine = data.Machine.get_one_for_update({'_id': machine.id}, conn=conn)
            machine.snapshots.remove(snap.id)
            machine.save(conn=conn)
    else:
        settings.raven.captureMessage('Error obtaining subject_id for delete snapshot request')

    return None


def process_other_actions(conn, action, vc):
    logger = logging.getLogger('action_others')
    logger.info('{}-{}->'.format(os.getpid(), action.id))

    try:
        request = data.Request.get_one_for_update({'_id': action.request}, conn=conn)
        request_type = request.type
        machine_ro = data.Machine.get_one({'_id': request.machine}, conn=conn)

        logger.info('{}-{}->{}|machine.state:{}|uuid:{}'.format(
                                                            os.getpid(),
                                                            action.id,
                                                            request.type,
                                                            machine_ro.state,
                                                            machine_ro.provider_id
        )
        )

        if machine_ro.state in ['undeployed']:
            request.state = 'aborted'
            request.save(conn=conn)
            action.lock = -1
            action.save(conn=conn)
            logger.info('request aborted, cannot be done on a machine in such a state')
            return

        if request_type == 'undeploy':
            new_machine_state = action_undeploy(request, machine_ro, vc)
        elif request_type == 'start':
            new_machine_state = action_start(request, machine_ro, vc)
        elif request_type == 'stop':
            new_machine_state = action_stop(request, machine_ro, vc)
        elif request_type == 'get_info':
            action_get_info(request, machine_ro, vc, action, conn)
            return
        elif request_type == 'take_screenshot':
            new_machine_state = action_take_screenshot(request, machine_ro, vc, conn)
        elif request_type == 'take_snapshot':
            new_machine_state = action_take_snapshot(request, machine_ro, vc, conn)
        elif request_type == 'restore_snapshot':
            new_machine_state = action_restore_snapshot(request, machine_ro, vc, conn)
        elif request_type == 'delete_snapshot':
            new_machine_state = action_delete_snapshot(request, machine_ro, vc, conn)
        else:
            logger.warn('unknown request: {} is going to succeed'.format(request_type))
            # will not be actually saved, only for setting request as failed
            new_machine_state = MachineState.FAILED

        if request_type in ['undeploy', 'start', 'stop']:  # only these requests can change machine state
            if new_machine_state is not None and new_machine_state.can_be_changed():
                machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
                machine.state = new_machine_state.value
                machine.save(conn=conn)

        request.state = 'success' if new_machine_state is not MachineState.FAILED else 'failed'
        request.save(conn=conn)
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)

        if request_type == 'start':
            enqueue_get_info_request(request, machine, conn)

    except Exception as e:
        settings.raven.captureException(exc_info=True)
        logger.error('Exception while processing action {}: '.format(action.id), exc_info=True)
        raise e

    finally:
        logger.info('{}-{}<-'.format(os.getpid(), action.id))


def signal_handler(signum, frame):
    logger.info('worker aborted by signal: {}'.format(signum))
    global process_actions
    process_actions = False


if __name__ == '__main__':

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = 'other'
    data.Connection.connect(
                                'conn1',
                                dsn=settings.app['db']['dsn']
    )
    vc = vcenter.VCenter()
    vc.connect()

    idle_counter = 0
    actions_counter = 0
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    process_actions = True
    while process_actions:
        time.sleep(settings.app['worker']['loop_initial_sleep'])
        with data.Connection.use('conn1') as conn:
            try:
                action = data.Action.get_one_for_update_skip_locked(
                                                                    {'type': mode, 'lock': 0},
                                                                    conn=conn
                )

                if action:
                    actions_counter += 1
                    if mode == 'deploy':
                        if actions_counter > settings.app['worker']['load_refresh_interval']:
                            actions_counter = 0
                            vc.refresh_destination_datastore()
                            vc.refresh_destination_resource_pool()
                        process_deploy_action(conn, action, vc)
                    else:
                        process_other_actions(conn, action, vc)
                else:
                    idle_counter += 1
                    if idle_counter > settings.app['worker']['idle_counter']:
                        vc.idle()
                        idle_counter = 0
                    time.sleep(settings.app['worker']['loop_idle_sleep'])
            except Exception:
                settings.raven.captureException(exc_info=True)
                logger.error(
                                'Exception while processing action: {}'.format(action.id),
                                exc_info=True
                )
                action.lock = -1
                action.save(conn=conn)

    logger.debug("Worker finished")
    time.sleep(1)
