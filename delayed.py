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


def host_info_obtainer(conn, vc):
    if Settings.app["vsphere"]["hosts_folder_name"]:
        hosts = vc.get_hosts_in_folder(Settings.app["vsphere"]["hosts_folder_name"])
        info = list(map(lambda host: {
            "name": host.name,
            "mo_ref": host._moId,
            'maintenance': host.runtime.inMaintenanceMode,
            'vms_count':len(host.vm),
            'vms_running_count': len(list(filter(lambda vm: vm.runtime.powerState == 'poweredOn', host.vm))),
            'connection_state': str(host.runtime.connectionState),
            'standby_mode': host.runtime.standbyMode,
            'local_templates': list(map(lambda vm: {
                "name": vm.name,
                "mo_ref": vm._moId
            },host.vm)),
            'local_datastores': list(map(lambda ds: {
                "name": ds.info.name,
                "mo_ref": ds._moId,
                "maintenance": not ds.summary.maintenanceMode == 'normal',
                "freeSpaceGB": ds.info.freeSpace/1024/1024/1024
            },host.datastore))
        }, hosts))
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
                new_host_info = data.HostRuntimeInfo( **item)
                new_host_info.created_at = datetime.datetime.now()
                new_host_info.save(conn=conn)


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
            host_info_obtainer(conn, vc)
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
