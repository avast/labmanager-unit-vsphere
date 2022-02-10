#!/usr/bin/env python3

import logging
import os
import socket
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


def obtain_statistics(cluster, endpoint, headers, host, port, stats_path):
    logger.info(f"sending statistics for cluster: {cluster}")
    # get data
    try:
        response = requests.get(
            f'{endpoint}capabilities',
            headers=headers,
            verify=False
        )
        if response.status_code != 200:
            logger.warning(f"cannot get capabilities of cluster {cluster}, stats not available!")

        out_json = response.json()
        maximum = out_json['responses'][0]['result']['slot_limit']
        free = out_json['responses'][0]['result']['free_slots']
    except Exception as ex:
        logger.warning(f"Exception while obtaining capabilities occurred: {ex}\n\nskipped\n")
        return

    consumed = maximum - free
    timestamp = str(datetime.strftime(datetime.now(), '%s'))
    out_string = f"{stats_path}.{cluster}.count {maximum} {timestamp}\n" \
                 f"{stats_path}.{cluster}.used {consumed} {timestamp}\n" \
                 f"{stats_path}.{cluster}.percent {consumed * 100 / maximum} {timestamp}\n"

    # open socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            # write data
            s.sendall(bytes(out_string, 'utf-8'))
            # close socket
    except Exception as ex:
        logger.warning(f"Exception while sending stats occurred: {ex}\n\nskipped\n")


if __name__ == '__main__':

    config_file = os.getenv('CONFIG', './statistics.yaml')
    env = os.getenv('ENV', 'production')
    config = {}
    logger = logging.getLogger(f'idle_ungeployer_{env}')

    while True:
        config = load_config(config_file, env)
        sleep_interval = config['interval']['sleep']
        logger.debug(config)
        for cluster_name in config['endpoints'].keys():
            if 'statistics' in config and config['statistics']['enabled']:
                obtain_statistics(
                    cluster_name,
                    config['endpoints'][cluster_name],
                    config['headers'],
                    config['statistics']['host'],
                    config['statistics']['port'],
                    config['statistics']['stats_path']
                )

            logger.info('')
        logger.info('=====================================')
        logger.info('')
        time.sleep(sleep_interval)
