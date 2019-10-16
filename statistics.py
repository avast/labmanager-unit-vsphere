#!/usr/bin/env python3

from datetime import datetime
import os
import yaml
import logging
import time
import requests
import json
import socket

logging.basicConfig(
    level='INFO',
    format='%(asctime)s %(thread)d %(threadName)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S.000Z'
)


def load_config(config_file, env):
    whole_config = yaml.safe_load(open(config_file, 'r').read())
    return whole_config[env]


def obtain_statistics(cluster, endpoint, headers, host, port, stats_path):
    logger.info("sending statistics for cluster: {}".format(cluster))
    # get data
    response = requests.get(
        '{}capabilities'.format(endpoint),
        headers=headers,
        verify=False
    )

    if response.status_code != 200:
        logger.warning(
            "cannot get capabilities of cluster {}, stats not available!".format(cluster)
        )

    out_json = response.json()
    maximum = out_json['responses'][0]['result']['slot_limit']
    free = out_json['responses'][0]['result']['free_slots']
    consumed = maximum - free
    timestamp = str(datetime.strftime(datetime.now(), '%s'))
    out_string = "{}.{}.count {} {}\n{}.{}.used {} {}\n{}.{}.percent {} {}\n".format(
        stats_path,
        cluster,
        maximum,
        timestamp,
        stats_path,
        cluster,
        consumed,
        timestamp,
        stats_path,
        cluster,
        consumed*100/maximum,
        timestamp
    )

    # open socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        # write data
        s.sendall(bytes(out_string, 'utf-8'))
        # close socket


if __name__ == '__main__':

    config_file = os.getenv('CONFIG', './statistics.yaml')
    env = os.getenv('ENV', 'production')
    config = {}
    logger = logging.getLogger('idle_ungeployer_{}'.format(env))

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
        logger.info('')
        logger.info('')
        time.sleep(sleep_interval)
