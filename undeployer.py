#!/usr/bin/env python3

from datetime import datetime
import os
import yaml
import logging
import time
import requests
import json

logging.basicConfig(
    level='INFO',
    format='%(asctime)s %(thread)d %(threadName)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S.000Z'
)


def load_config(config_file, env):
    whole_config = yaml.safe_load(open(config_file, 'r').read())
    return whole_config[env]


def check_request_type(endpoint, headers, request_id, request_type):
    response = requests.get(
        '{}requests/{}'.format(endpoint, request_id),
        headers=headers
    )
    if response.status_code == 200:
        return response.json()['responses'][0]['result']['request_type'] == request_type
    return False


def undeploy_machine(endpoint, headers, machine_id):
    # return
    response = requests.delete(
        '{}machines/{}'.format(endpoint, machine_id),
        headers=headers
    )
    return response.status_code == 200


def check_and_undeploy(
                        endpoint_name,
                        endpoint,
                        headers,
                        state,
                        interval_to_live,
                        last_request_type
):
    # logger.debug('{}: {} -> {}'.format(endpoint_name, endpoint, headers))
    response = requests.get('{}machines?state={}'.format(endpoint, state), headers=headers)
    num_machines = 0
    num_undeployed = 0
    if response.status_code == 200:
        for machine in response.json()["responses"][0]["result"]:
            num_machines += 1
            machine_id = machine["id"]
            machine_name = machine["machine_name"]
            last_request_id = machine["requests"][-1]
            datetime_obj = datetime.strptime(machine["modified_at"], '%Y-%m-%d %H:%M:%S')
            seconds_alive = (datetime.now()-datetime_obj).total_seconds()
            if check_request_type(endpoint, headers, last_request_id, last_request_type) and \
               seconds_alive > interval_to_live:
                logger.info('{}: machine: {} is to be undeployed ({:.2f} hours) {}'.format(
                    endpoint_name,
                    machine_name,
                    seconds_alive/60/60,
                    machine["modified_at"]
                ))
                undeploy_machine(endpoint, headers, machine_id)
                num_undeployed += 1
            else:
                logger.info('{}: machine: {} is to be kept ({:.2f} hours) {}'.format(
                    endpoint_name,
                    machine_name,
                    seconds_alive/60/60,
                    machine["modified_at"]
                ))
    logger.info('{}: {} in the state: {}, {} undeployed'.format(
        endpoint_name,
        num_machines,
        state,
        num_undeployed
    ))


def ensure_capacity(
                        endpoint_name,
                        endpoint,
                        headers,
                        required_free_capacity_percentage
):
    response = requests.get(
        '{}capabilities'.format(endpoint),
        headers=headers
    )
    if response.status_code != 200:
        logger.warning(
            "cannot get capabilities of cluster {}, stats not available!".format(cluster)
        )
        return

    out_json = response.json()
    slots_max = out_json['responses'][0]['result']['slot_limit']
    slots_free = out_json['responses'][0]['result']['free_slots']

    free_slots_required = int(slots_max * required_free_capacity_percentage/100)
    logger.info("Endpoint {}: {} free, {} required to be free".format(
        endpoint_name,
        slots_free,
        free_slots_required
    ))

    if slots_free > free_slots_required:
        logger.info("-> machine removal not needed, there is enough free slots.")
        return

    to_be_removed = free_slots_required - slots_free
    logger.info("-> machine removal NEEDED, {} machine(s) will be removed.".format(to_be_removed))

    machine_seconds = dict()
    for state in "created", "deployed", "stopped":
        response = requests.get('{}machines?state={}'.format(endpoint, state), headers=headers)
        if response.status_code == 200:
            all_response_machines = response.json()["responses"][0]["result"]
            for machine in all_response_machines:
                machine_id = machine["id"]
                datetime_obj = datetime.strptime(machine["modified_at"], '%Y-%m-%d %H:%M:%S')
                seconds_alive = (datetime.now()-datetime_obj).total_seconds()
                machine_seconds[machine_id] = seconds_alive

    machine_seconds_sorted = sorted(machine_seconds.items(), key=lambda kv: kv[1], reverse=True)
    machine_ids_to_be_deleted = machine_seconds_sorted[0:to_be_removed] \
        if count(machine_seconds_sorted) > to_be_removed else machine_seconds_sorted
    for machine in machine_ids_to_be_deleted:
        logger.info("-> deleting machine with id {}".format(machine[0]))
        del_response = requests.delete('{}machines/{}'.format(
            endpoint,
            machine[0]),
            headers=headers
        )

        logger.info("-> deleting machine {}".format(
            "SUCCEEDED" if del_response.status_code == 200 else "FAILED"
        ))


if __name__ == '__main__':

    config_file = os.getenv('CONFIG', './undeployer.yaml')
    env = os.getenv('ENV', 'production')
    config = {}
    logger = logging.getLogger('idle_ungeployer_{}'.format(env))

    while True:
        config = load_config(config_file, env)
        sleep_interval = config['interval']['sleep']
        stopped_duration = config['interval']['stopped_duration']
        deployed_duration = config['interval']['stopped_duration']
        running_duration = config['interval']['running_duration']
        logger.debug(config)
        for cluster_name in config['endpoints'].keys():
            check_and_undeploy(
                cluster_name,
                config['endpoints'][cluster_name],
                config['headers'],
                'stopped',
                stopped_duration,
                'stop'
            )

            check_and_undeploy(
                cluster_name,
                config['endpoints'][cluster_name],
                config['headers'],
                'running',
                running_duration,
                'get_info'
            )

            check_and_undeploy(
                cluster_name,
                config['endpoints'][cluster_name],
                config['headers'],
                'deployed',
                deployed_duration,
                'deploy'
            )

            ensure_capacity(
                cluster_name,
                config['endpoints'][cluster_name],
                config['headers'],
                int(config['required_free_capacity_percentage'])
            )

            logger.info('')
        logger.info('')
        logger.info('')
        time.sleep(sleep_interval)
