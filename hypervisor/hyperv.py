import sys
import logging
import functools
import inspect
import time
import subprocess
import os
import pystache
import copy
import re


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
        try:
            hyperv_logger.debug(f"deploy: started ({template_name} -> {machine_name})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["NEW_VM_NAME"] = machine_name
            replacements["TEMPLATE_NAME"] = Settings.app['hyperv']['templatemap'][template_name]
            #print(replacements)
            ex.execute("deployVmFromTemplate.t", replacements)
            ex.log_last_error_stream("deploy: ")
            hyperv_logger.debug(str(ex))
            return machine_name
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("deploy: finished")

    @log_to(hyperv_logger)
    def config_network(self, device_uuid, **kwargs):
        try:
            hyperv_logger.debug(f"config_network: started ({device_uuid})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["NEW_VM_NAME"] = device_uuid
            #print(replacements)
            ex.execute("setVmNetwork.t", replacements)
            ex.log_last_error_stream("config_network: ")
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("config_network: finished")

    @log_to(hyperv_logger)
    def get_machine_info(self, machine_uuid):
        res = {"mo_ref": "", "nos_id":"", "machine_search_link":"NO_MACHINE_SEARCH_LINK",
               "machine_name": machine_uuid, "power_state": "", 'ip_addresses': [],
        }
        #get machine info
        try:
            hyperv_logger.debug(f"get_machine_info: started ({machine_uuid})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["VM_NAME"] = machine_uuid
            # print(replacements)
            ex.execute("getVmInfo.t", replacements)
            results = ex.get_results_from_last_run()
            hyperv_logger.info(f"get_machine_info: {results}")
            for line in results:
                if "OUT::MAC=" in line:
                    mac = str(line).replace("OUT::MAC=", "")
                    res["nos_id"] = f"{Settings.app['nosid_prefix']}{mac}"
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("get_machine_info: finished")

        return res

    @log_to(hyperv_logger)
    def start(self, machine_uuid):
        try:
            hyperv_logger.debug(f"start: started ({machine_uuid})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["VM_NAME"] = machine_uuid
            #print(replacements)
            ex.execute("startVm.t", replacements)
            ex.log_last_error_stream("start: ")
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("start: finished")

    @log_to(hyperv_logger)
    def stop(self, machine_uuid):
        try:
            hyperv_logger.debug(f"stop: started ({machine_uuid})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["VM_NAME"] = machine_uuid
            #print(replacements)
            ex.execute("stopVm.t", replacements)
            ex.log_last_error_stream("stop: ")
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("stop: finished")

    @log_to(hyperv_logger)
    def undeploy(self, machine_uuid):
        try:
            hyperv_logger.debug(f"undeploy: started ({machine_uuid} -> XXX)")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["VM_NAME"] = machine_uuid
            ex.execute("undeployVm.t", replacements)
            ex.log_last_error_stream("undeploy: ")
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("undeploy: finished")

    @log_to(hyperv_logger)
    def reset(self, machine_uuid):
        try:
            hyperv_logger.debug(f"reset: started ({machine_uuid})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["VM_NAME"] = machine_uuid
            #print(replacements)
            ex.execute("resetVm.t", replacements)
            ex.log_last_error_stream("reset: ")
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("reset: finished")

    @log_to(hyperv_logger)
    def take_screenshot(self, machine_uuid: str, store_to: str = 'db') -> Union[bytes, str]:
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def take_snapshot(self, machine_uuid, snapshot_name) -> bool:
        try:
            hyperv_logger.debug(f"take_snapshot: started ({device_uuid})")
            ex = HypervExecutor()
            replacements = copy.deepcopy(Settings.app['hyperv']['replacements'])
            replacements["NEW_VM_NAME"] = device_uuid
            replacements["SNAPSHOT_NAME"] = snapshot_name
            #print(replacements)
            ex.execute("takeSnapshot.t", replacements)
            ex.log_last_error_stream("take_snapshot: ")
            hyperv_logger.debug(str(ex))
        except Exception as exc:
            raise exc
        finally:
            hyperv_logger.debug("take_snapshot: finished")

    @log_to(hyperv_logger)
    def revert_snapshot(self, machine_uuid, snapshot_name):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

    @log_to(hyperv_logger)
    def remove_snapshot(self, machine_uuid, snapshot_name):
        hyperv_logger.warning(f"Method >>{inspect.currentframe().f_code.co_name}<<"
                              f" has not been implemented yet in {sys.modules[__name__]}")

class HypervExecutor:
    def __init__(self):
        self.last_return_code = None
        self.last_err = None
        self.last_out = None
        self.last_time = 0
        self.templates_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'hyperv.templates'
        )
    def execute(self, template, replacements):
        template_str = self._read_template(template)

        input_data = pystache.render(template_str, replacements)
        start_time = time.time()
        #hyperv_logger.debug(input_data)
        #return

        executable_with_params = [
            Settings.app['hyperv']['ssh'],
            f"{Settings.app['hyperv']['username']}@{Settings.app['hyperv']['servers'][0]}",
            "-i", Settings.app['hyperv']['key']
        ]

        if Settings.app['hyperv']['ssh_extra_params'] != []:
            for param in Settings.app['hyperv']['ssh_extra_params']:
                executable_with_params.append(param)

        result = subprocess.run(
            executable_with_params,
            input = input_data,
            capture_output = True,
            text = True,
            timeout = 45
        )
        stop_time = time.time()
        #hyperv_logger.debug(f"exec result: {result}")
        self.last_return_code = result.returncode
        self.last_err = result.stderr
        self.last_out = result.stdout
        self.last_time = stop_time - start_time

    def log_last_error_stream(self, prefix=""):
        if self.last_err is None:
            hyperv_logger.warning(f"{prefix} There is nothing in last stderr stream!")
            return
        for line in self.last_err.split('\n'):
            hyperv_logger.debug(f"{prefix}{line}")

    def get_results_from_last_run(self):
        res = []

        delim = "\n"
        if self.last_out is None:
            hyperv_logger.warning("get_results_from_last_run: last stdout was none, nothing can be parsed")
            return []
        sp = self.last_out.split(delim)
        pattern = re.compile("^OUT::")
        for l in sp:
            if pattern.match(l):
                res.append(l)

        return res

    def _read_template(self, template):
        template_path = os.path.join(self.templates_path, template)
        with open(template_path, "r", encoding="utf-8") as file:
            return file.read()

    def __str__(self):
        return f"return: {self.last_return_code}\nit took: {self.last_time}s\nerr: {self.last_err}\nout: {self.last_out}"

Hypervisor = Hyperv
# eof
