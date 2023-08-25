import logging
import time
from sanic import Blueprint

import web.modeltr as data
from web.settings import Settings
from web.modeltr.enums import MachineState

logger = logging.getLogger(__name__)

capabilities = Blueprint('capabilities')


class Capabilities:
    _free_slots = 0
    _slot_limit = Settings.app['slot_limit']
    _last_check = 0
    _labels = Settings.app['labels'] + ["unit:{}".format(Settings.app['unit_name'])]

    @staticmethod
    async def fetch(forced=False):
        used_slots = Capabilities._slot_limit - Capabilities._free_slots
        logger.debug("Capabilities last check: {}".format(Capabilities._last_check))
        caching_period = Settings.app['service']['capabilities']['caching_period']
        caching_threshold = Settings.app['service']['capabilities']['caching_enabled_threshold']
        if forced or \
           used_slots > int(Capabilities._slot_limit*(caching_threshold/100)) or \
           int(time.time()) - Capabilities._last_check > caching_period:
            logger.debug("Real capabilities fetch from db in progress...")
            with data.Connection.use() as conn:
                if Settings.app["vsphere"]["hosts_folder_name"]:
                    ready_hosts1 = data.HostRuntimeInfo.get({"maintenance": "false"}, conn=conn)
                    ready_hosts = [host for host in ready_hosts1 if host.to_be_in_maintenance is False]
                    vm_per_host = int(Settings.app["slot_limit"] / len(data.HostRuntimeInfo.get({}, conn=conn)))
                    Capabilities._slot_limit = vm_per_host * len(ready_hosts)
                    Capabilities._free_slots = min(
                        len(data.DeployTicket.get({'taken': 0, 'enabled': 'true'}, conn=conn)),
                        Capabilities._slot_limit
                    )

                else:
                    used_slots = \
                        len(data.Machine.get({'state': MachineState.RUNNING.value}, conn=conn)) + \
                        len(data.Machine.get({'state': MachineState.DEPLOYED.value}, conn=conn)) + \
                        len(data.Machine.get({'state': MachineState.CREATED.value}, conn=conn))
                    Capabilities._free_slots = max(Capabilities._slot_limit - used_slots, 0)
            Capabilities._last_check = int(time.time())
            logger.debug("Real capabilities fetch finished")

    @staticmethod
    def get_free_slots():
        return Capabilities._free_slots

    @staticmethod
    def get_slot_limit():
        return Capabilities._slot_limit

    @staticmethod
    def get_labels():
        return Capabilities._labels


@capabilities.route('/capabilities', methods=['GET'])
async def cap_get_info(request):
    await Capabilities.fetch()
    return {
        'result': {
            'slot_limit': Capabilities.get_slot_limit(),
            'free_slots': Capabilities.get_free_slots(),
            'labels': Capabilities.get_labels(),
        },
        'is_last': True
    }
