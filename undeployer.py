#!/usr/bin/env python3

import logging
import os
import time
from datetime import datetime

import requests
import yaml

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
        f'{endpoint}requests/{request_id}',
        headers=headers
    )
    if response.status_code == 200:
        return response.json()['responses'][0]['result']['request_type'] == request_type
    return False


def undeploy_machine(endpoint, headers, machine_id):
    response = requests.delete(
        f'{endpoint}machines/{machine_id}',
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
    unit_state_name = f'{endpoint_name}[{state}]'
    logger.info(f'{unit_state_name}: examining state: {state}, ensure to live for {interval_to_live} secs.')
    try:
        response = requests.get(f'{endpoint}machines?state={state}', headers=headers)
    except Exception:
        logger.warning(f'{unit_state_name}: error communicating with endpoint: {endpoint}\nSKIPPED!!')
        return

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
            is_request_type_ok = check_request_type(endpoint, headers, last_request_id, last_request_type)
            hours = seconds_alive / 60 / 60
            ts = machine["modified_at"]
            if is_request_type_ok and seconds_alive > interval_to_live:
                logger.info(f'{unit_state_name}: machine: {machine_name} is to be undeployed ({hours:.2f} hours) {ts}')
                undeploy_machine(endpoint, headers, machine_id)
                num_undeployed += 1
            else:
                logger.info(f'{unit_state_name}: machine: {machine_name} is to be kept ({hours:.2f} hours) {ts}')
    else:
        logger.error(f'{unit_state_name}: error getting machines in state: {state}, response: {response.status_code}')

    logger.info(f'{unit_state_name}: {num_machines} in the state: {state}, {num_undeployed} undeployed')


def ensure_capacity(endpoint_name, endpoint, headers, required_free_capacity_percentage):

    unit_state_name = f'{endpoint_name}[ensure {required_free_capacity_percentage}%]'
    logger.info(f'{unit_state_name}: ensuring capacity: {required_free_capacity_percentage} percent')
    response = requests.get(f'{endpoint}capabilities', headers=headers)
    if response.status_code != 200:
        logger.warning(f"cannot get capabilities of {unit_state_name}, stats not available ({response.status_code})!")
        return

    out_json = response.json()
    slots_max = out_json['responses'][0]['result']['slot_limit']
    slots_free = out_json['responses'][0]['result']['free_slots']
    free_slots_required = int(slots_max * required_free_capacity_percentage/100)
    logger.info(f"{unit_state_name}: {slots_free} free, {free_slots_required} required to be free")

    if slots_free > free_slots_required:
        logger.info("-> machine removal not needed, there is enough free slots.")
        return

    to_be_removed = free_slots_required - slots_free
    logger.info(f"-> machine removal NEEDED, {to_be_removed} machine(s) should be removed.")

    machine_seconds = dict()
    state = "stopped"
    try:
        response = requests.get(f'{endpoint}machines?state={state}', headers=headers)
        if response.status_code == 200:
            all_response_machines = response.json()["responses"][0]["result"]
            for machine in all_response_machines:
                machine_id = machine["id"]
                datetime_obj = datetime.strptime(machine["modified_at"], '%Y-%m-%d %H:%M:%S')
                seconds_alive = (datetime.now()-datetime_obj).total_seconds()
                machine_seconds[machine_id] = seconds_alive
    except Exception:
        logger.error('-> error obtaining machines to be undeployed')

    machine_seconds_sorted = sorted(machine_seconds.items(), key=lambda kv: kv[1], reverse=True)
    machine_ids_to_be_deleted = machine_seconds_sorted[0:to_be_removed] \
        if len(machine_seconds_sorted) > to_be_removed else machine_seconds_sorted
    logger.info(f"-> machine removal NEEDED, {len(machine_ids_to_be_deleted)} machine(s) will be removed.")
    for machine in machine_ids_to_be_deleted:
        logger.info(f"-> deleting machine with id {machine[0]}")
        del_response = requests.delete(f'{endpoint}machines/{machine[0]}', headers=headers)
        res_str = 'SUCCEEDED' if del_response.status_code == 200 else 'FAILED'
        logger.info(f"-> deleting machine {res_str}")


def get_custom_config(where, what, default):
    if where is None:
        return default
    else:
        return where.get(what, default)


if __name__ == '__main__':

    config_file = os.getenv('CONFIG', './undeployer.yaml')
    env = os.getenv('ENV', 'production')
    config = {}
    logger = logging.getLogger(f'idle_undeployer_{env}')

    while True:
        config = load_config(config_file, env)
        sleep_interval = config['interval']['sleep']
        logger.debug(config)
        for cluster_name in config['endpoints'].keys():
            states_dict = {
                'stopped': {
                    'last_action_type': 'stop',
                    'duration': config['interval']['stopped_duration']
                },
                'running': {
                    'last_action_type': 'get_info',
                    'duration': config['interval']['running_duration']
                },
                'deployed': {
                    'last_action_type': 'deploy',
                    'duration': config['interval']['deployed_duration']
                },
            }

            for state, data in states_dict.items():
                check_and_undeploy(
                    cluster_name,
                    config['endpoints'][cluster_name],
                    config['headers'],
                    state,
                    get_custom_config(config.get(f'interval_{cluster_name}'), f'{state}_duration', data['duration']),
                    data['last_action_type']
                )

            ensure_capacity(
                cluster_name,
                config['endpoints'][cluster_name],
                config['headers'],
                int(get_custom_config(
                    config.get('required_free_capacity_percentage'),
                    cluster_name,
                    int(config['required_free_capacity_percentage_default']),
                ))
            )

            logger.info('')
        logger.info('')
        logger.info('')
        time.sleep(sleep_interval)
