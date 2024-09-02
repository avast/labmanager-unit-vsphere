#!/usr/bin/env python3

import datetime
import logging
import os
import random
import re
import signal
import sys
import time
import socket

import vcenter.vcenter as vcenter
import web.modeltr as data
from web.modeltr.enums import MachineState, RequestState, RequestType
from web.settings import Settings, set_context_var, reset_context_var
from web.stats import stats_increment_metric_worker as stats_increment_metric
from web.stats import stats_add_timing_metric_worker as stats_add_timing_metric

logger = logging.getLogger(__name__)


def acquire_deploy_ticket():
    result = {}
    if Settings.app["vsphere"]["hosts_folder_name"]:
        ticket = None
        ticket_id = -1
        ticket_hostmoref = ''
        start_ticket_obtaining = time.time()
        with data.Connection.use('qconn') as conn:
            while ticket is None:
                query = {'taken': 0, 'enabled': 'true'}
                ticket = data.DeployTicket.get_one_for_update_skip_locked(query, conn=conn)
                time.sleep(0.4)
            ticket.taken = 1
            ticket_id = ticket.id
            ticket_hostmoref = ticket.host_moref
            ticket.save(conn=conn)
        ticket_obtaining_time = time.time() - start_ticket_obtaining
        result["host_moref"] = ticket_hostmoref
        result["id"] = ticket_id
        logger.debug(f"Deploy ticket obtained in {ticket_obtaining_time} seconds")
    return result


def alter_deploy_ticket(ticket, vm_moref):
    if Settings.app["vsphere"]["hosts_folder_name"]:
        with data.Connection.use('qconn') as conn:
            ticket = data.DeployTicket.get_one_for_update({"_id": ticket["id"]}, conn=conn)
            ticket.assigned_vm_moref = vm_moref
            ticket.save(conn=conn)


def release_deploy_ticket(vm_moref):
    if Settings.app["vsphere"]["hosts_folder_name"]:
        if vm_moref != '':
            try:
                with data.Connection.use('qconn') as conn:
                    ticket = data.DeployTicket.get_one({"assigned_vm_moref": vm_moref}, conn=conn)
                    if ticket:
                        ticket = data.DeployTicket.get_one_for_update({"assigned_vm_moref": vm_moref}, conn=conn)
                        ticket.assigned_vm_moref = ''
                        ticket.taken = 0
                        ticket.save(conn=conn)
                    else:
                        logger.debug(f"Deployticket for machine: {vm_moref} not found")

            except Exception as ex:
                logger.warning(f"Error releasing deploy ticket for {vm_moref}: {repr(ex)}", exc_info=True)
        else:
            logger.warning("release_deploy_ticket called with empty vm_moref!")

def release_deploy_ticket_id(id):
    if Settings.app["vsphere"]["hosts_folder_name"]:
        with data.Connection.use('qconn') as conn:
            ticket = data.DeployTicket.get_one({"_id": id}, conn=conn)
            if(ticket):
                ticket.assigned_vm_moref = ''
                ticket.taken = 0
                ticket.save(conn=conn)
            else:
                logger.warning("Db error when handling release_deploy_ticket_id")


def get_template(labels):
    for l in labels:
        matches = re.match('template:(.*)', l)
        if matches:
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
        set_context_var('http_verb', f"D,r:{action.request},a:{action.id},m:{machine_ro.id},mstate:{machine_ro.state}")
        logger.info(f'{os.getpid()}-{action.id}->deploy|machine.state: {machine_ro.state}')


        if machine_ro.state == MachineState.UNDEPLOYED:
            logger.warning(f"Attempting to deploy undeployed machine, machine.id: {machine_ro.id}")
            # TODO: make sure that it doesn't break anything and remove "if"
            #if Settings.app["vsphere"]["hosts_folder_name"]:
            raise RuntimeError('Undeployed machine cannot be deployed')

        stats_increment_metric('deploy-request')
        template = get_template(machine_ro.labels)

        if Settings.app['vsphere']['default_network_name'] and Settings.app['vsphere']['force_default_network_name']:
            network_interface = Settings.app['vsphere']['default_network_name']
        else:
            network_interface = get_network_interface(machine_ro.labels)

        inventory_folder = get_inventory_folder(machine_ro.labels)
        machine_info = {'nos_id': ''}
        if Settings.app['unit_name']:
            output_machine_name = f'{template}-{Settings.app["unit_name"]}-{request.machine}'
        else:
            output_machine_name = f'{template}-{request.machine}'

        has_running_label = machine_ro.has_feat_running_label()

        try:
            uuid = ''
            if Settings.app["vsphere"]["hosts_folder_name"]:
                ticket = acquire_deploy_ticket()
                try:
                    machine = vc.deploy_via_ticket(template, output_machine_name, ticket)
                    alter_deploy_ticket(ticket, machine["mo_ref"])
                    uuid = machine["uuid"]
                except Exception as e:
                    logger.warning(
                        f"An error occurred when trying to deploy {template} as {output_machine_name} ({repr(e)})"
                    )
                    release_deploy_ticket_id(ticket['id'])
                    raise e
            else:
                uuid = vc.deploy(template,
                                 output_machine_name,
                                 running=has_running_label,
                                 inventory_folder=inventory_folder)
            if network_interface:
                vc.config_network(uuid, interface_name=network_interface)
            machine_info = vc.get_machine_info(uuid)
        except Exception as e:
            Settings.raven.captureException(exc_info=True)
            logger.warning('Exception deploying machine: ', exc_info=True)
            raise e

        if not machine_info['nos_id']:
            result = vc.stop(uuid)
            if result is False:
                logger.debug('vc.stop failed (nos_id problem)')
            vc.undeploy(uuid)
            release_deploy_ticket(machine_info['mo_ref'])
            raise RuntimeError(f"NOS ID hasn't been returned for machine {uuid}")

        machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
        machine.provider_id = uuid
        machine.nos_id = machine_info['nos_id']
        machine.machine_name = machine_info['machine_name']
        machine.machine_search_link = machine_info['machine_search_link']
        machine.machine_moref = machine_info['mo_ref']
        request.state = RequestState.SUCCESS
        request.save(conn=conn)
        is_machine_running = machine_info['power_state'] == 'poweredOn'
        machine.state = MachineState.RUNNING if is_machine_running is True else MachineState.DEPLOYED
        machine.save(conn=conn)
        if is_machine_running:
            # enqueue get machine info only if enabled (currently only for online kitchen units)
            if Settings.app['enqueue_get_machine_info'] is True:
                logger.debug('enqueue get info request to obtain IPs for instant cloned machine...')
                enqueue_get_info_request(machine, conn)
            else:
                logger.debug(f'skipping get info request to obtain IPs for instant cloned machine...')
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)
        stats_increment_metric('deploy-ok')
    except Exception as e:
        stats_increment_metric('deploy-failed')
        Settings.raven.captureException(exc_info=True)
        logger.error('action_deploy exception: ', exc_info=True)


        request.state = RequestState.FAILED
        request.save(conn=conn)
        machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
        machine.state = MachineState.FAILED
        machine.save(conn=conn)
        logger.debug(f'updating action to be finished [Exception]--{repr(e)}')
        action.lock = -1
        action.save(conn=conn)
    finally:
        logger.info(f'{os.getpid()}-{action.id}<-')
        reset_context_var('http_verb')


def action_undeploy(request, machine, vc):
    try:
        stats_increment_metric('undeploy-request')
        machine_info = vc.get_machine_info(machine.provider_id)
        result = vc.stop(machine.provider_id)
        if result is False:
            logger.debug(f'vc.stop failed (action_undeploy) ({machine.provider_id}) in state {machine.state}')
        vc.undeploy(machine.provider_id)
    except Exception:
        try:
            logger.warning(f"error in action_undeploy on a machine ({machine.provider_id}) in state {machine.state}")
        except Exception:
            pass
        Settings.raven.captureException(exc_info=True)
        return MachineState.FAILED
    finally:
        try:
            if machine_info["mo_ref"] != '':
                release_deploy_ticket(machine_info["mo_ref"])
        except Exception:
            logger.warning(f"error in action_undeploy, deploy ticket probably not released", exc_info=True)

    return MachineState.UNDEPLOYED


def action_start(request, machine, vc):
    stats_increment_metric('start-request')
    vc.start(machine.provider_id)
    return MachineState.RUNNING


def action_stop(request, machine, vc):
    try:
        stats_increment_metric('stop-request')
        machine_stopped = vc.stop(machine.provider_id)
        if not machine_stopped:
            logger.debug('vc.stop failed (action_stop)')
    finally:
        try:
            release_deploy_ticket(machine.machine_moref)
        except:
            logger.warning("action_stop: error while releasing deploy ticket")
        return MachineState.STOPPED


def action_reset(request, machine, vc):
    stats_increment_metric('restart-request')
    vc.reset(machine.provider_id)
    return None


def action_get_info(request, machine_ro, vc, action, conn):
    logger.debug(request.to_dict())
    stats_increment_metric('getinfo-request')
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
        request.state = RequestState.SUCCESS
        action.lock = -1
    else:
        machine.save(conn=conn)
        request.state = RequestState.DELAYED
        action.repetitions -= 1
        action.next_try = datetime.datetime.now() + datetime.timedelta(
            seconds=random.randint(action.delay, action.delay+3)
        )
        action.lock = 1
    request.save(conn=conn)
    action.save(conn=conn)
    if len(info['ip_addresses']) == 0:
        approx_duration_seconds = (Settings.app['worker']["getinfo_default_repetition_count"] - action.repetitions)*11
        stats_add_timing_metric("getinfo-approxduration",  approx_duration_seconds)
        logger.debug(f'TIMING FIRED {approx_duration_seconds}')


def enqueue_get_info_request(machine, conn):
    # create another task to get info about that machine
    logger.debug(f'creating another get_info action for {machine.id}')
    new_request = data.Request(type=RequestType.GET_INFO, machine=str(machine.id))
    new_request.save(conn=conn)
    machine.requests.append(new_request.id)
    machine.save(conn=conn)
    data.Action(
            type='other',
            request=new_request.id,
            repetitions=Settings.app['worker']["getinfo_default_repetition_count"],
            delay=10,
            next_try=datetime.datetime.now() + datetime.timedelta(seconds=5)
    ).save(conn=conn)


def action_take_screenshot(request, machine, vc, conn):
    stats_increment_metric('takess-request')
    ss_destination = Settings.app['service']['screenshot_store']
    if ss_destination not in ['db', 'hcp']:
        logger.warning(f'wrong configuration for screenshot_store: {ss_destination}')
        ss_destination = 'db'

    screenshot_data = vc.take_screenshot(machine.provider_id, store_to=ss_destination)
    if request.subject_id:
        ss = data.Screenshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        if screenshot_data:
            if ss_destination == 'hcp':
                ss.image_base64 = screenshot_data
                ss.status = 'hcpstored'
            else:
                ss.image_base64 = screenshot_data.decode("utf-8")
                ss.status = 'obtained'
        else:
            ss.image_base64 = ""
            ss.status = "error"
        ss.save(conn=conn)
    else:
        Settings.raven.captureMessage('Error obtaining subject_id from Request')
    return None


def action_take_snapshot(request, machine, vc, conn):
    if request.subject_id:
        stats_increment_metric('snaptake-request')
        snap_ro = data.Snapshot.get_one({'_id': request.subject_id}, conn=conn)
        result = vc.take_snapshot(machine_uuid=machine.provider_id, snapshot_name=snap_ro.get_uniq_name())
        snap = data.Snapshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        snap.status = 'success' if result is True else 'failed'
        snap.save(conn=conn)
        if result is True:
            # attach snapshot from machine if creating was successful
            machine = data.Machine.get_one_for_update({'_id': machine.id}, conn=conn)
            machine.snapshots.append(snap.id)
            machine.save(conn=conn)

    else:
        Settings.raven.captureMessage('Error obtaining subject_id for take snapshot request')
    return None


# TODO deduplicate with 'action_take_snapshot()' later
def action_restore_snapshot(request, machine, vc, conn):
    if request.subject_id:
        stats_increment_metric('snaprestore-request')
        snap_ro = data.Snapshot.get_one({'_id': request.subject_id}, conn=conn)
        result = vc.revert_snapshot(machine_uuid=machine.provider_id, snapshot_name=snap_ro.get_uniq_name())
        snap = data.Snapshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        snap.status = 'success' if result is True else 'failed'
        snap.save(conn=conn)
    else:
        Settings.raven.captureMessage('Error obtaining subject_id for restore snapshot request')

    return None


# TODO deduplicate with 'action_take_snapshot()' later
def action_delete_snapshot(request, machine, vc, conn):
    if request.subject_id:
        stats_increment_metric('snapdelete-request')
        snap_ro = data.Snapshot.get_one({'_id': request.subject_id}, conn=conn)
        result = vc.remove_snapshot(machine_uuid=machine.provider_id, snapshot_name=snap_ro.get_uniq_name())
        snap = data.Snapshot.get_one_for_update({'_id': request.subject_id}, conn=conn)
        snap.status = 'success' if result is True else 'failed'
        snap.save(conn=conn)
        if result is True:
            # detach snapshot from machine if remove was successful
            machine = data.Machine.get_one_for_update({'_id': machine.id}, conn=conn)
            machine.snapshots.remove(snap.id)
            machine.save(conn=conn)
    else:
        Settings.raven.captureMessage('Error obtaining subject_id for delete snapshot request')

    return None


def process_other_actions(conn, action, vc):
    logger = logging.getLogger('action_others')
    logger.info(f'{os.getpid()}-{action.id}->')

    try:
        request = data.Request.get_one_for_update({'_id': action.request}, conn=conn)
        request_type = request.type
        machine_ro = data.Machine.get_one({'_id': request.machine}, conn=conn)

        m = f'{os.getpid()}-{action.id}->{request.type}|machine.state:{machine_ro.state}|uuid:{machine_ro.provider_id}'
        set_context_var('http_verb', f"O,r:{action.request},a:{action.id},m:{machine_ro.id},mstate:{machine_ro.state}")
        logger.info(m)


        if request_type is not RequestType.UNDEPLOY:
            if not machine_ro.state.can_be_changed():
                request.state = RequestState.ABORTED
                request.save(conn=conn)
                action.lock = -1
                action.save(conn=conn)
                logger.info('request aborted, cannot be done on a machine in such a state')
                return

        if request_type is RequestType.UNDEPLOY:
            new_machine_state = action_undeploy(request, machine_ro, vc)
        elif request_type is RequestType.START:
            new_machine_state = action_start(request, machine_ro, vc)
        elif request_type is RequestType.STOP:
            new_machine_state = action_stop(request, machine_ro, vc)
        elif request_type is RequestType.RESTART:
            new_machine_state = action_reset(request, machine_ro, vc)
        elif request_type is RequestType.GET_INFO:
            action_get_info(request, machine_ro, vc, action, conn)
            return
        elif request_type is RequestType.TAKE_SCREENSHOT:
            new_machine_state = action_take_screenshot(request, machine_ro, vc, conn)
        elif request_type is RequestType.TAKE_SNAPSHOT:
            new_machine_state = action_take_snapshot(request, machine_ro, vc, conn)
        elif request_type is RequestType.RESTORE_SNAPSHOT:
            new_machine_state = action_restore_snapshot(request, machine_ro, vc, conn)
        elif request_type is RequestType.DELETE_SNAPSHOT:
            new_machine_state = action_delete_snapshot(request, machine_ro, vc, conn)
        else:
            # this should not happen
            Settings.raven.captureMessage(f'Unhandled request type: {request_type}')
            # will not be actually saved, only for setting request as failed
            new_machine_state = MachineState.FAILED

        if request_type.can_change_machine_state():
            # save new state iff old state can be changed and we have some new state
            if new_machine_state is not None and machine_ro.state.can_be_changed():
                machine = data.Machine.get_one_for_update({'_id': request.machine}, conn=conn)
                machine.state = new_machine_state
                machine.save(conn=conn)

        request.state = RequestState.SUCCESS if new_machine_state is not MachineState.FAILED else RequestState.FAILED
        request.save(conn=conn)
        logger.debug('updating action to be finished...')
        action.lock = -1
        action.save(conn=conn)

        if request_type is RequestType.START:
            # enqueue get machine info only if enabled (currently only for online kitchen units)
            if Settings.app['enqueue_get_machine_info'] is True:
                logger.debug(f'enqueueing get info request')
                enqueue_get_info_request(machine, conn)
            else:
                logger.debug(f'skipping get info request')

    except Exception as e:
        Settings.raven.captureException(exc_info=True)
        logger.error(f'Exception while processing action {action.id}: ', exc_info=True)
        raise e

    finally:
        logger.info(f'{os.getpid()}-{action.id}<-')
        reset_context_var('http_verb')


def signal_handler(signum, frame):
    logger.info(f'worker aborted by signal: {signum}')
    global process_actions
    process_actions = False


if __name__ == '__main__':

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = 'other'

    logger.info(f'socket default timeout: {socket.getdefaulttimeout()}')
    socket_default_timeout = Settings.app['vsphere']['socket_default_timeout']
    if socket_default_timeout is not None:
        socket.setdefaulttimeout(socket_default_timeout)
        logger.info(f'set socket timeout: {socket.getdefaulttimeout()}')

    data.Connection.connect('conn1',
                            dsn=Settings.app['db']['dsn'],
                            socket_reusability=Settings.app['db']['socket_reusability']
    )
    if Settings.app["vsphere"]["hosts_folder_name"]:
        data.Connection.connect('qconn', dsn=Settings.app['db']['dsn'])
    vc = vcenter.VCenter()
    vc.connect()

    idle_counter = 0
    actions_counter = 0
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    process_actions = True
    while process_actions:
        time.sleep(Settings.app['worker']['loop_initial_sleep'])
        with data.Connection.use('conn1') as conn:
            try:
                action = data.Action.get_one_for_update_skip_locked({'type': mode, 'lock': 0}, conn=conn)
                if action:
                    actions_counter += 1
                    process_start_time = time.time()
                    if mode == 'deploy':
                        if actions_counter > Settings.app['worker']['load_refresh_interval']:
                            actions_counter = 0
                            vc.refresh_destination_datastore()
                            vc.refresh_destination_resource_pool()
                        process_deploy_action(conn, action, vc)
                    else:
                        process_other_actions(conn, action, vc)
                    try:
                        # log processing duration
                        process_duration = round(time.time() - process_start_time, 1)
                        request_ro = data.Request.get_one({'_id': action.request}, conn=conn)
                        logger.debug(f'Processing action {request_ro.type.value} took {process_duration} seconds')
                    except Exception as e:
                        logger.warning('Error while logging action processing:', exc_info=True)
                else:
                    idle_counter += 1
                    if idle_counter > Settings.app['worker']['idle_counter']:
                        vc.idle()
                        idle_counter = 0
                    time.sleep(Settings.app['worker']['loop_idle_sleep'])
            except Exception:
                Settings.raven.captureException(exc_info=True)
                logger.error(f'Exception while processing action: {action.id}', exc_info=True)
                action.lock = -1
                action.save(conn=conn)

    logger.debug("Worker finished")
    time.sleep(1)
