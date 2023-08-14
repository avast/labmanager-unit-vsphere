#!/usr/bin/env python3

import datetime
import logging
import signal
import time

import web.modeltr as data
from web.modeltr.enums import RequestState
from web.settings import Settings
import vcenter.vcenter as vcenter

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    global process_actions
    logger.info(f'worker aborted by signal: {signum}')
    process_actions = False


def _safe_array_map(input_array, func):
    result = []
    try:
        for item in input_array:
            try:
                result.append(func(item))
            except Exception as iex:
                logger.warning(f"safe_array_map failed due to: {iex}")
    except Exception:
        return []
    return result


def save_to_db(info, conn):
    for item in info:
        host_info = data.HostRuntimeInfo.get_one_for_update(
            {'name': item['name']},
            conn=conn)
        if host_info:
            host_info.maintenance = item['maintenance']
            host_info.vms_count = item['vms_count']
            host_info.vms_running_count = item['vms_running_count']
            host_info.connection_state = item['connection_state']
            host_info.standby_mode = item['standby_mode']
            host_info.local_templates = item['local_templates']
            host_info.local_datastores = item['local_datastores']
            host_info.save(conn=conn)
        else:
            new_host_info = data.HostRuntimeInfo(**item)
            new_host_info.created_at = datetime.datetime.now()
            new_host_info.save(conn=conn)


def delete_unwanted_documents(info, conn):
    host_names = [item["name"] for item in info]
    hosts_to_be_deleted = []
    ids_to_be_deleted = []
    for hostinfo in data.HostRuntimeInfo.get({}, conn=conn):
        if hostinfo.name not in host_names:
            hosts_to_be_deleted.append(hostinfo.name)
    for host_name in hosts_to_be_deleted:
        host = data.HostRuntimeInfo.get({'name': host_name}, conn=conn)
        ids_to_be_deleted.append(host[0].id)
    for host_id in ids_to_be_deleted:
        data.HostRuntimeInfo.delete({'_id': host_id}, conn=conn)
        logger.debug(f'host: {host_id} deleted from database')


# noinspection PyProtectedMember
def host_info_obtainer(conn, vc):
    if Settings.app["vsphere"]["hosts_folder_name"]:
        start_host_info_obtainer = time.time()
        hosts = vc.get_hosts_in_folder(Settings.app["vsphere"]["hosts_folder_name"])
        info = _safe_array_map(hosts, lambda host: {
            "name": host.name,
            "mo_ref": host._moId,
            'maintenance': host.runtime.inMaintenanceMode,
            'vms_count': len(host.vm),
            'vms_running_count': len(_safe_array_map(host.vm, lambda vm: vm.runtime.powerState == 'poweredOn')),
            'connection_state': str(host.runtime.connectionState),
            'standby_mode': host.runtime.standbyMode,
            'local_templates': _safe_array_map(host.vm, lambda vm: {
               "name": vm.name,
               "mo_ref": vm._moId
            }),
            'local_datastores': _safe_array_map(host.datastore, lambda ds: {
                "name": ds.info.name,
                "mo_ref": ds._moId,
                "maintenance": not ds.summary.maintenanceMode == 'normal',
                "freeSpaceGB": ds.info.freeSpace / 1024 / 1024 / 1024
            })
        })

        save_to_db(info, conn)

        # hosts that are currently not present in vmware folder must be deleted from db as well
        delete_unwanted_documents(info, conn)

        logger.info(f'host_info_obtainer finished successfully ' +
                    f'in: {time.time() - start_host_info_obtainer}')


if __name__ == '__main__':

    data.Connection.connect('conn2', dsn=Settings.app['db']['dsn'])

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    vc = None
    if Settings.app["vsphere"]["hosts_folder_name"]:
        vc = vcenter.VCenter()
        vc.connect(quick=True)

    process_actions = True
    while process_actions:

        with data.Connection.use('conn2') as conn:
            try:
                host_info_obtainer(conn, vc)
            except Exception:
                Settings.raven.captureException(exc_info=True)
                logger.error('Could not obtain host information: ', exc_info=True)

        with data.Connection.use('conn2') as conn:
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

        time.sleep(Settings.app['delayed']['sleep'])

    logger.debug("Delayed finished")
