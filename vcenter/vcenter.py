from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl

from web.settings import Settings as settings

import sys
import ssl
import atexit
import time
import logging


class VCenter():

    def __init__(self):
        self._connected = False
        self.content = None
        self.__logger = logging.getLogger(__name__)

    def __check_connection(self):
        try:
            objView = self.content.viewManager.CreateContainerView(self.content.rootFolder,
                                                                   [vim.Datastore],
                                                                   True)
            objView.Destroy()
        except Exception:
            self.connect()

    def connect(self):
        context = ssl._create_unverified_context()

        si = SmartConnect(
                            host=settings.app['vsphere']['host'],
                            user=settings.app['vsphere']['username'],
                            pwd=settings.app['vsphere']['password'],
                            port=settings.app['vsphere']['port'],
                            sslContext=context
        )

        if not si:
            self.__logger.error(
                'Cannot connect to specified host using specified username and password'
            )

        self.content = si.content
        self._connected = True

    def idle(self):
        self.__check_connection()
        self.__logger.debug('keeping connection alive: {}'.format(self.content.about.vendor))

    def __search(self, _list, snapshot_name):
        for item in _list:
            if(item.name == snapshot_name):
                self.__logger.debug('snapshot found: {}'.format(item))
                return(item.snapshot)

            if item.childSnapshotList != []:
                return self.__search(item.childSnapshotList, snapshot_name)

    def search_for_snapshot(self, vm, snapshot_name):
        for item in vm.snapshot.rootSnapshotList:
            if(item.name == snapshot_name):
                return(item.snapshot)

            if item.childSnapshotList != []:
                return self.__search(item.childSnapshotList, snapshot_name)

        raise ValueError('snapshot {} cannot be found'.format(snapshot_name))
        return None

    def deploy(self, template, machine_name):
        self.__check_connection()

        objView = self.content.viewManager.CreateContainerView(self.content.rootFolder,
                                                               [vim.VirtualMachine],
                                                               True)
        vm = None
        for item in objView.view:
            if item.name == template:
                self.__logger.debug('machine: {}\n{}--{}---\n'.format(
                                                                        dir(item),
                                                                        item._GetMoId(),
                                                                        item.name
                ))
                self.__logger.debug('parent: {}\n'.format(item.parent._GetMoId()))
                self.__logger.debug('datastores: {}\n'.format(item.datastore[0]))

                try:
                    self.__logger.debug('snapshot: {}\n'.format(dir(item.snapshot.currentSnapshot)))
                    snap = self.search_for_snapshot(
                                                    item,
                                                    settings.app['vsphere']['default_snapshot_name']
                    )

                    # for full clone, use 'moveAllDiskBackingsAndDisallowSharing'
                    spec = vim.vm.CloneSpec(
                        location=vim.vm.RelocateSpec(
                            datastore=item.datastore[0],
                            diskMoveType='createNewChildDiskBacking',
                            host=item.runtime.host,
                            transform=vim.vm.RelocateSpec.Transformation.sparse
                        ),
                        powerOn=False,
                        snapshot=snap,
                        template=False,
                    )

                    task = item.CloneVM_Task(
                        item.parent,
                        machine_name,
                        spec
                    )

                    vm = self.wait_for_task(task)
                    if not vm:
                        raise RuntimeError("virtual machine hasn't been returned")

                    self.__logger.debug('Task finished with status: {}'.format(vm.config.uuid))
                except Exception as e:
                    self.__logger.warn('pyvmomi related exception: ', exc_info=True)
        objView.Destroy()

        return vm.config.uuid

    def undeploy(self, uuid):
        self.__check_connection()

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)
        if vm:
            self.__logger.debug('found vm: {}'.format(vm.config.uuid))
            task = vm.Destroy_Task()
            self.wait_for_task(task)
            self.__logger.debug('vm killed')
        else:
            raise Exception('machine {} not found'.format(uuid))

    def start(self, uuid):
        self.__check_connection()

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)
        if vm:
            self.__logger.debug('found vm: {}'.format(vm.config.uuid))
            task = vm.PowerOnVM_Task()
            self.wait_for_task(task)
            self.__logger.debug('vm powered on')
        else:
            raise Exception('machine {} not found'.format(uuid))

    def stop(self, uuid):
        self.__check_connection()

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)
        if vm:
            self.__logger.debug('found vm: {}'.format(vm.config.uuid))
            task = vm.PowerOffVM_Task()
            self.wait_for_task(task)
            self.__logger.debug('vm powered on')
        else:
            raise Exception('machine {} not found'.format(uuid))

    def config_network(self, uuid, **kwargs):
        self.__logger.debug('config_network')
        self.__check_connection()

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)

        for device in vm.config.hardware.device:
            if type(device) == vim.vm.device.VirtualE1000 or \
               type(device) == vim.vm.device.VirtualE1000e or \
               type(device) == vim.vm.device.VirtualPCNet32 or \
               type(device) == vim.vm.device.VirtualVmxnet or \
               type(device) == vim.vm.device.VirtualVmxnet2 or \
               type(device) == vim.vm.device.VirtualVmxnet3:
                device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo(
                    deviceName=kwargs['interface_name']
                )

                device_config_spec = vim.VirtualDeviceConfigSpec(
                    operation=vim.VirtualDeviceConfigSpecOperation('edit'),
                    device=device
                )

                machine_config_spec = vim.vm.ConfigSpec(
                    deviceChange=[device_config_spec]
                )
                task = vm.ReconfigVM_Task(spec=machine_config_spec)
                self.wait_for_task(task)

    def get_machine_info(self, uuid):
        self.__check_connection()
        result = {'ip_addresses': []}

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)
        try:
            if vm:
                self.__logger.debug('found vm: {}'.format(vm.config.uuid))
                for adapter in vm.guest.net:
                    for ip in adapter.ipConfig.ipAddress:
                        result['ip_addresses'].append(ip.ipAddress)
                self.__logger.debug('get machine info end')
        except Exception:
            self.__logger.debug('get machine info failed')
        finally:
            return result

    def wait_for_task(self, task):
        time.sleep(3)
        while (task.info.state == 'running' or task.info.state == 'queued'):
            self.__logger.debug('Progress {}% | Task: {}\r'.format(
                task.info.progress,
                task.info.description.message if task.info.description else 'unnamed'
            ))
            time.sleep(1)
        self.__logger.debug('Task finished with status: {}, return value: {}'.format(
            task.info.state,
            task.info.result,
        )
        )
        return task.info.result
