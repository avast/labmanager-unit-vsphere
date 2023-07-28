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
    for count in hash.values():
        if count != max:
            return False
    return True
    #filtered = list(filter(lambda v: v == max, hash.values()))
    #return len(filtered) == len(hash.values())
    #return all(filter(lambda v: v == max, hash.values()))


def disable_tickets_in_maintenance(hosts):
    number_of_hosts = len(hosts)
    if number_of_hosts > 0:
        logger.debug(f"Disabling tickets on hosts ({number_of_hosts}) in maintenance...")
        for moref in hosts:
            tickets = []
            with data.Connection.use('conn2') as conn:
                tickets = data.DeployTicket.get({"host_moref": moref, "enabled": 'true'}, conn=conn)
            for ticket in tickets:
                with data.Connection.use('conn2') as qc:
                    ticket = data.DeployTicket.get_one_for_update({"_id": ticket.id}, conn=qc)
                    ticket.enabled = False
                    ticket.save(conn=qc)
        logger.debug(f"Disabled tickets on hosts ({number_of_hosts}) in maintenance.")


def get_last_separator_ticket_id(tickets):
    fake_id = None
    for ticket in tickets:
        if ticket.host_moref == "SEPARATOR":
            if fake_id is None:
                fake_id = ticket.id
            else:
                if int(fake_id) < int(ticket.id):
                    fake_id = ticket.id
    return fake_id


def cleanup_old_tickets_if_too_many(fake_id, tickets):
    counter = 0
    if fake_id is not None:
        old_tickets = list(filter(lambda ticket: int(ticket.id) < int(fake_id), tickets))
        for old_ticket in old_tickets:
            if old_ticket.enabled is False:
                counter += 1
                with data.Connection.use('quick') as qc:
                    data.DeployTicket.delete({"_id": old_ticket.id}, conn=qc)
                if counter > 25: break
    if counter > 0:
        logger.debug(f"Proactively deleted {counter} old unwanted tickets")


def create_new_separator_ticket():
    start_ticket_id = None
    try:
        with data.Connection.use('quick') as qc:
            fake_ticket = data.DeployTicket(
                created_at=datetime.datetime.now(),
                host_moref="SEPARATOR",
                assigned_vm_moref="vm-SEPARATOR",
                enabled=False
            )
            fake_ticket.save(conn=qc)
            start_ticket_id = fake_ticket.id
    finally:
        return start_ticket_id


def disable_tickets(old_tickets_ids):
    for id in old_tickets_ids:
        with data.Connection.use('quick') as qc:
            ticket = data.DeployTicket.get_one_for_update({"_id": id}, conn=qc)
            ticket.enabled = False
            ticket.save(conn=qc)


def get_current_ticket_statistics(ready_hosts, start_ticket_id):
    current_ticket_statistics = {}
    for host in ready_hosts:
        # count taken ones
        with data.Connection.use('conn2') as conn:
            current_ticket_statistics[host.mo_ref] = \
                len(data.DeployTicket.get({"host_moref": host.mo_ref, "taken": 1}, conn=conn))
        # count newly enabled
        with data.Connection.use('conn2') as conn:
            current_ticket_statistics[host.mo_ref] += len(list(
                filter(
                    lambda ticket: int(ticket.id) > int(start_ticket_id),
                    data.DeployTicket.get({"host_moref": host.mo_ref, 'enabled': 'true', 'taken': 0}, conn=conn)
                )
            ))
    logger.debug(f"current_ticket_statistics: {current_ticket_statistics}")
    return current_ticket_statistics


def ensure_correct_count_of_new_tickets_is_enabled(new_tickets, vm_per_host, ticket_statistics_dict):
    for ticket in new_tickets:
        if check_all_running(ticket_statistics_dict, vm_per_host):
            break
        with data.Connection.use('quick') as qc:
            ticket_rw = data.DeployTicket.get_one_for_update({"_id": ticket.id}, conn=qc)
            host = ticket_rw.host_moref
            if host in ticket_statistics_dict:
                if ticket_statistics_dict[host] < vm_per_host:
                    ticket_rw.enabled = True
                    ticket_statistics_dict[host] += 1
                    logger.info(f"Enabled ticket ({ticket.id}) on host {host}")
                ticket_rw.save(conn=qc)

def get_all_new_tickets(separator_ticket_id):
    data_from_db = []
    with data.Connection.use('conn2') as conn:
        data_from_db = data.DeployTicket.get({"enabled": 'false'}, conn=conn)
    return list(filter(lambda ticket: int(ticket.id) > int(separator_ticket_id), data_from_db))


class Ticketeer:

    def __init__(self, conn=None):
        self.slot_limit = Settings.app["slot_limit"]
        self.hosts = data.HostRuntimeInfo.get({}, conn=conn)

        # maintenance field represents actual state of the host
        # to_be_in_maintenance is set by the unit to signal that the host will be in maintenance soon
        # and the task putting into maintenance is running and hopefully will be finished soon
        ready_hosts = data.HostRuntimeInfo.get({"maintenance": "false"}, conn=conn)
        self.ready_hosts = list(filter(lambda host: host.to_be_in_maintenance == False, ready_hosts))

        self.vm_per_host = int(self.slot_limit / len(self.hosts))
        real_slot_limit = self.vm_per_host * len(ready_hosts)

        # get morefs of all hosts
        self.hosts_morefs = list(map(lambda host: host.mo_ref, self.hosts))

        # get morefs of ready hosts
        self.ready_hosts_morefs = list(map(lambda host: host.mo_ref, ready_hosts))

        # disable all hosts that are in maintenance
        disable_tickets_in_maintenance(list(set(self.hosts_morefs) - set(self.ready_hosts_morefs)))

        self.tickets = data.DeployTicket.get({}, conn=conn)
        # first search for the last SEPARATOR
        self.fake_id = get_last_separator_ticket_id(self.tickets)

        # there are only active tickets
        self.actual_tickets = [] if self.fake_id is None else \
            list(filter(lambda ticket: int(ticket.id) > int(self.fake_id), self.tickets))

    def should_tickets_be_reshuffled(self):
        len(self.actual_tickets) != self.vm_per_host * len(self.hosts)

    def re_shuffle(self):
        logger.info("ticket imbalance detected...")

        # create a fake ticket that separates old ones and new ones
        start_ticket_id = create_new_separator_ticket()

        # gets all old ticket ids
        old_tickets = data.DeployTicket.get({"enabled": "true"}, conn=conn)
        old_tickets_ids = list(map(lambda ticket: ticket.id,
                                   filter(lambda ticket: int(ticket.id) < int(start_ticket_id), old_tickets)))

        # create new tickets, every one in disabled state
        generate_tickets_in_correct_order(self.hosts_morefs, self.vm_per_host)

        disable_tickets(old_tickets_ids)


    def finish_re_shuffling(self):
        start_ticket_id = self.fake_id

        # get all new tickets that are not enabled
        new_tickets = get_all_new_tickets(start_ticket_id)

        ticket_statistics_dict = get_current_ticket_statistics(self.ready_hosts, start_ticket_id)

        ensure_correct_count_of_new_tickets_is_enabled(new_tickets, self.vm_per_host, ticket_statistics_dict)

    def cleanup(self):
        cleanup_old_tickets_if_too_many(self.fake_id, self.tickets)


def ticketeer(conn):
    slot_limit = Settings.app["slot_limit"]
    hosts = data.HostRuntimeInfo.get({}, conn=conn)

    # maintenance field represents actual state of the host
    # to_be_in_maintenance is set by the unit to signal that the host will be in maintenance soon
    # and the task putting into maintenance is running and hopefully will be finished soon
    ready_hosts = data.HostRuntimeInfo.get({"maintenance": "false"}, conn=conn)
    ready_hosts = list(filter(lambda host: host.to_be_in_maintenance == False, ready_hosts))

    vm_per_host = int(slot_limit/len(hosts))
    real_slot_limit = vm_per_host * len(ready_hosts)

    # get morefs of all hosts
    hosts_morefs = list(map(lambda host: host.mo_ref, hosts))

    # get morefs of ready hosts
    ready_hosts_morefs = list(map(lambda host: host.mo_ref, ready_hosts))

    # disable all hosts that are in maintenance
    disable_tickets_in_maintenance(list(set(hosts_morefs)-set(ready_hosts_morefs)))

    tickets = data.DeployTicket.get({}, conn=conn)
    # first search for the last SEPARATOR
    fake_id = get_last_separator_ticket_id(tickets)

    # there are only active tickets
    actual_tickets = [] if fake_id is None else list(filter(lambda ticket: int(ticket.id) > int(fake_id), tickets))

    if len(actual_tickets) != vm_per_host * len(hosts):
        logger.info("ticket imbalance detected...")

        # create a fake ticket that separates old ones and new ones
        start_ticket_id = create_new_separator_ticket()

        # gets all old ticket ids
        old_tickets = data.DeployTicket.get({"enabled": "true"}, conn=conn)
        old_tickets_ids = list(map(lambda ticket: ticket.id,
                                   filter(lambda ticket: int(ticket.id) < int(start_ticket_id), old_tickets)))

        # create new tickets, every one in disabled state
        generate_tickets_in_correct_order(hosts_morefs, vm_per_host)

        disable_tickets(old_tickets_ids)

    else:
        # contiguously enable up to vm_per_host on enabled hosts
        start_ticket_id = fake_id

        # get all new tickets that are not enabled
        new_tickets = get_all_new_tickets(start_ticket_id)

        ticket_statistics_dict = get_current_ticket_statistics(ready_hosts, start_ticket_id)

        ensure_correct_count_of_new_tickets_is_enabled(new_tickets, vm_per_host, ticket_statistics_dict)

    cleanup_old_tickets_if_too_many(fake_id, tickets)


if __name__ == '__main__':

    Settings.app['document_abstraction']['warn_0_records'] = False
    data.Connection.connect('conn2', dsn=Settings.app['db']['dsn'])
    data.Connection.connect('quick', dsn=Settings.app['db']['dsn'])

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    vc = None
    if Settings.app["vsphere"]["hosts_folder_name"]:
        vc = vcenter.VCenter()
        vc.connect(quick=True)

    process_actions = True
    revolution = 0
    while process_actions:
        with data.Connection.use('conn2') as conn:
            try:
                logger.info(f"proceeding {revolution}....\n")
                #ticketeer(conn)
                ticketeer = Ticketeer(conn=conn)
                if ticketeer.should_tickets_be_reshuffled():
                    ticketeer.re_shuffle()
                else:
                    ticketeer.finish_re_shuffling()
                ticketeer.cleanup()

            except Exception:
                Settings.raven.captureException(exc_info=True)
                logger.error('Exception while processing request: ', exc_info=True)
        revolution += 1
        time.sleep(Settings.app['ticketeer']['sleep'])

    logger.debug(f"Deploy Ticketeer has finished")
