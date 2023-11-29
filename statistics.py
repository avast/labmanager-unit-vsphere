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


def send_stats_graphite(cluster, machines_max, machines_used, load_percentage, config):
    timestamp = str(datetime.strftime(datetime.now(), '%s'))
    stats_path = config['stats_path']
    out_string = f"{stats_path}.{cluster}.count {machines_max} {timestamp}\n" \
                 f"{stats_path}.{cluster}.used {machines_used} {timestamp}\n" \
                 f"{stats_path}.{cluster}.percent {load_percentage} {timestamp}\n"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((config['host'], config['port']))
            s.sendall(bytes(out_string, 'utf-8'))
    except Exception as ex:
        logger.warning(f"Exception while sending stats occurred for {cluster}: {ex}\n\nskipped\n")


def send_stats_statsd(cluster, machines_max, machines_used, load_percentage, config):
    stats_path = config['stats_path']
    out_string = f"{stats_path}.{cluster}.count:{machines_max}|g\n" \
                 f"{stats_path}.{cluster}.used:{machines_used}|g\n" \
                 f"{stats_path}.{cluster}.percent:{load_percentage}|g\n"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((config['host_statsd'], config['port_statsd']))
            s.sendall(bytes(out_string, 'utf-8'))
    except Exception as ex:
        logger.warning(f"Exception while sending statsd stats occurred for {cluster}: {ex}\n\nskipped\n")


def obtain_statistics(cluster, endpoint, headers, config):
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
    try:
        percent = consumed * 100 / maximum
    except:
        percent = 0
    if config['host_statsd'] and config['port_statsd']:
        send_stats_statsd(cluster, maximum, consumed, percent, config)
    else:
        send_stats_graphite(cluster, maximum, consumed, percent, config)


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
                    config['statistics']
                )

            logger.info('')
        logger.info('=====================================')
        logger.info('')
        time.sleep(sleep_interval)
