#!/usr/bin/env python3

import datetime
import logging
import signal
import time
import threading

import web.modeltr as data
from web.settings import Settings
import random

logger = logging.getLogger(__name__)


def signal_handler(signum, frame):
    global process_actions
    logger.info(f'worker aborted by signal: {signum}')
    process_tickets = False


def kill_thread(vm_id):
    time.sleep(5)
    data.Connection.connect(f'conn-{vm_id}', dsn=Settings.app['db']['dsn'])
    while (True):
        time.sleep(1)
        try:
            test_data_lock.acquire(blocking=True)
            if (int(datetime.datetime.now().timestamp()) > (test_data[vm_id]['started'] + test_data[vm_id]['wait'])) and \
                    test_data[vm_id]['ticket_id'] != 0:
                logger.info(f"Killing id: {vm_id}, it ran: {int(datetime.datetime.now().timestamp()) - test_data[vm_id]['started']}s, should run:{test_data[vm_id]['wait']}")
                while True:
                    with data.Connection.use(f'conn-{vm_id}') as conn:
                        ticket_rw: data.DeployTicket = data.DeployTicket.get_one_for_update({"_id": test_data[vm_id]['ticket_id']}, conn=conn)
                        if ticket_rw:
                            ticket_rw.assigned_vm_moref = ""
                            ticket_rw.taken = 0
                            ticket_rw.save(conn=conn)
                            test_data[vm_id]['vm_moref'] = ''
                            test_data[vm_id]['ticket_id'] = 0
                            break
                        else:
                            logger.info(f"cannot obtain ticket with id {test_data[vm_id]['ticket_id']}")
                            time.sleep(0.4)
                            continue
                break
        except Exception as e:
            logger.info("Killing error ", exc_info=True)
        finally:
            test_data_lock.release()


if __name__ == '__main__':
    app_started = datetime.datetime.now().timestamp()
    data.Connection.connect('conn2', dsn=Settings.app['db']['dsn'])

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    count = 20
    test_data = []
    test_data_lock = threading.Lock()
    test_threads = []

    process_actions = True
    while process_actions:
        logger.info("Generating jobs....")

        for i in range(count):
            test_data.append({
                'wait': random.randint(30, 50),
                'started': 0,  # time machine was started
                'ticket_id': 0,
                'vm_moref': f"vm-{random.randint(1000, 20000)}",
                'host': '',
            })
        logger.info("Generating jobs done.")

        time.sleep(5)
        try:
            logger.info("Deploying vms....")
            for i in range(count):
                now = datetime.datetime.now()
                ticket = None
                with data.Connection.use('conn2') as conn:
                    while ticket is None:
                        query = {'taken': 0, 'enabled': 'true'}
                        ticket = data.DeployTicket.get_one_for_update_skip_locked(query, conn=conn)
                        if ticket is None:
                            logger.info(f"DeployTicket for machine {i} cannot be obtained")
                        time.sleep(0.4)
                    start_ticket_manipulation = time.time()
                    try:
                        test_data_lock.acquire(blocking=True)
                        test_data[i]['started'] = int(datetime.datetime.now().timestamp())
                        test_data[i]['ticket_id'] = ticket.id
                        test_data[i]['host'] = ticket.host_moref
                        ticket.assigned_vm_moref = test_data[i]['vm_moref']
                    finally:
                        test_data_lock.release()
                    ticket.taken = 1
                    ticket.save(conn=conn)

                    ticket_manipulation_length = time.time() - start_ticket_manipulation
                    if ticket_manipulation_length > 0.6:
                        logger.warning(f"DeployTicket for machine {i} obtained & processed in " +
                                       f"{ticket_manipulation_length} s")
                    else:
                        logger.info(f"DeployTicket for machine {i} obtained & processed in " +
                                    f"{ticket_manipulation_length} s")
                # now we consider that the machine can be started on a specific host
                logger.info(f"vm: {test_data[i]['vm_moref']} deployed on {test_data[i]['host']}" +
                            f"({test_data[i]['ticket_id']}) at {test_data[i]['started']}")

                # start vmkill thread (it may happen that available number of vms is less than 20)
                thr = threading.Thread(target=kill_thread, name=f"[killer_for_vm_{i}]", args=(i,))
                test_threads.append(thr)
                thr.start()

            logger.info("Deploying vms done.")

            logger.info("Killing vms....")
            while len(test_threads) > 0:
                filtered = list(filter(lambda thr: thr.is_alive(),test_threads))
                logger.info(f"still running {len(filtered)} vms.")
                for thr in filtered:
                    thr.join(2)
                test_threads = filtered
                time.sleep(1)
            logger.info("Killing vms done.")

        except Exception:
            Settings.raven.captureException(exc_info=True)
            logger.error('Exception while processing request: ', exc_info=True)
        break

    logger.debug(f"Test Acquier finished in {datetime.datetime.now().timestamp()-app_started} s")
