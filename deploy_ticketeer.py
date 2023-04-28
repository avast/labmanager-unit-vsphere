#!/usr/bin/env python3

import datetime
import logging
import signal
import time

import web.modeltr as data
from web.settings import Settings
import vcenter.vcenter as vcenter

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    global process_actions
    logger.info(f'worker aborted by signal: {signum}')
    process_actions = False


def generate_tickets_in_correct_order(host_names, max_slots):
    for i in range(max_slots):
        for host in host_names:
            with data.Connection.use('quick') as qc:
                data.DeployTicket(created_at=datetime.datetime.now(), host_moref=host, enabled=False).save(conn=qc)


def check_all_running(hash: dict, max):
    filt = list(filter(lambda v: v == max, hash.values()))
    return len(filt) == len(hash.values())


def disable_tickets_in_maintenance(hosts):
    logger.debug("Disabling hosts in maintenance...")
    for moref in hosts:
        tickets = []
        with data.Connection.use('conn2') as conn:
            tickets = data.DeployTicket.get({"host_moref":moref, "enabled": 'true'}, conn=conn)
        for ticket in tickets:
            with data.Connection.use('conn2') as qc:
                ticket = data.DeployTicket.get_one_for_update({"_id": ticket.id}, conn=qc)
                ticket.enabled = False
                ticket.save(conn=qc)
    logger.debug("Disabed hosts in maintenance...")

def fix_imbalance(conn):
    slot_limit = Settings.app["slot_limit"]
    hosts = data.HostRuntimeInfo.get({}, conn=conn)
    # THIS is only an approximation >>>>>
    ready_hosts = data.HostRuntimeInfo.get({"maintenance": "false"}, conn=conn)

    vm_per_host = int(slot_limit/len(hosts))
    real_slot_limit = vm_per_host * len(ready_hosts)

    # get morefs of all hosts
    hosts_morefs = list(map(lambda host: host.mo_ref, hosts))

    # get morefs of ready hosts
    ready_hosts_morefs = list(map(lambda host: host.mo_ref, ready_hosts))

    # disable all hosts that are in maintenance
    disable_tickets_in_maintenance(list(set(hosts_morefs)-set(ready_hosts_morefs)))

    tickets = data.DeployTicket.get({}, conn=conn)
    # first search for the last FAKE
    fake_id = None
    for ticket in tickets:
        if ticket.host_moref == "FAKE":
            fake_id = ticket.id

    # there are only active tickets
    actual_tickets = list(filter(lambda ticket: int(ticket.id) > int(fake_id), tickets))

    if len(actual_tickets) != vm_per_host * len(hosts):
        logger.info("ticket imbalance detected...")
        start_ticket_id = None
        # create fake ticket that separates old ones and new ones
        with data.Connection.use('quick') as qc:
            fake_ticket = data.DeployTicket(created_at=datetime.datetime.now(), host_moref="FAKE", assigned_vm_moref="vm-FAKE", enabled=False)
            fake_ticket.save(conn=qc)
            start_ticket_id = fake_ticket.id

        # gets all old ticket ids
        old_tickets = data.DeployTicket.get({"enabled": "true"}, conn=conn)
        old_tickets_ids = list(map(lambda ticket: ticket.id, filter(lambda ticket:int(ticket.id) < int(start_ticket_id), old_tickets)))
        # create new tickets, every one in disabled state
        generate_tickets_in_correct_order(hosts_morefs, vm_per_host)

        for id in old_tickets_ids:
            with data.Connection.use('quick') as qc:
                 ticket = data.DeployTicket.get_one_for_update({"_id": id}, conn=qc)
                 ticket.enabled = False
                 ticket.save(conn=qc)
    else:
        # contiguously enable up to vm_per_host on enabled hosts
        start_ticket_id = None
        # create fake ticket that separates old ones and new ones
        with data.Connection.use('quick') as qc:
            fake_tickets = data.DeployTicket.get({"host_moref": "FAKE"}, conn=qc)
            start_ticket_id = fake_tickets[-1].id

        # get all new tickets that are not enabled
        data_from_db = []
        with data.Connection.use('conn2') as conn:
            data_from_db = data.DeployTicket.get({"enabled": 'false'}, conn=conn)
        new_tickets = list(filter(lambda ticket: int(ticket.id) > int(start_ticket_id), data_from_db))

        # get currently running on each host
        running = {}
        for host in ready_hosts:
            #count running ones
            with data.Connection.use('conn2') as conn:
                running[host.mo_ref] = len(data.DeployTicket.get({"host_moref": host.mo_ref, "taken": 1}, conn=conn))
            #count new enabled
            with data.Connection.use('conn2') as conn:
                running[host.mo_ref] += len(list(filter(lambda ticket: int(ticket.id) > int(start_ticket_id), data.DeployTicket.get({"host_moref": host.mo_ref, 'enabled': 'true'}, conn=conn))))
        print(running)

        for ticket in new_tickets:
            if check_all_running(running, vm_per_host):
                break
            with data.Connection.use('quick') as qc:
                ticket_rw = data.DeployTicket.get_one_for_update({"_id": ticket.id}, conn=qc)
                host = ticket_rw.host_moref
                if host in running:
                    if running[host] < vm_per_host:
                        ticket_rw.enabled = True
                        running[host] += 1
                    ticket_rw.save(conn=qc)

    # cleanup old tickets if too many
    logger.debug("Proactively deleting old unwanted tickets")
    old_tickets = list(filter(lambda ticket: int(ticket.id) < int(fake_id), tickets))
    counter = 0
    for old_ticket in old_tickets:
        if old_ticket.enabled == False:
            counter += 1
            with data.Connection.use('quick') as qc:
                data.DeployTicket.delete({"_id": old_ticket.id}, conn=qc)
            if counter > 25: break
    logger.debug("deleted old unwanted tickets")


if __name__ == '__main__':

    data.Connection.connect('conn2', dsn=Settings.app['db']['dsn'])
    data.Connection.connect('quick', dsn=Settings.app['db']['dsn'])

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
                logger.info("proceeding....")
                fix_imbalance(conn)

            except Exception:
                Settings.raven.captureException(exc_info=True)
                logger.error('Exception while processing request: ', exc_info=True)

        time.sleep(3)

    logger.debug(f"Deploy Ticketeer finished, took:")
