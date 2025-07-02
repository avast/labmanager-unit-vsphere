import sys
import logging
import functools
import inspect

from typing import Union, Optional
from web.settings import Settings, log_to

# logger for logging in this file
hyperv_logger = logging.getLogger(__name__)


class Hyperv:

    def __init__(self):
        pass

    @log_to(hyperv_logger)
    def connect(self, quick=False):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    def idle(self):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    def refresh_destination_datastore(self):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    def refresh_destination_resource_pool(self):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def deploy_via_ticket(self, template_name, machine_name, deploy_ticket):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def deploy(self, template_name, machine_name, running, **kwargs):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")
        print("foo")

    @log_to(hyperv_logger)
    def config_network(self, device_uuid, **kwargs):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def get_machine_info(self, machine_uuid):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def start(self, machine_uuid):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def stop(self, machine_uuid):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def undeploy(self, machine_uuid):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def reset(self, machine_uuid):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def take_screenshot(self, machine_uuid: str, store_to: str = 'db') -> Union[bytes, str]:
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def take_snapshot(self, machine_uuid, snapshot_name) -> bool:
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def revert_snapshot(self, machine_uuid, snapshot_name):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def remove_snapshot(self, machine_uuid, snapshot_name):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")


Hypervisor = Hyperv
# eof
