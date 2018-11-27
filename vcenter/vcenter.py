from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl

from web.settings import Settings as settings

import sys
import ssl
import atexit
import time
import logging
import re

class VCenter():

    def __init__(self):
        self._connected = False
        self.content = None
        self.__logger = logging.getLogger(__name__)
        self.vm_folders = VCenter.VmFolders(self)

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

    def __single_snapshot_search(self, _list, snapshot_name):
        for item in _list:
            if(item.name == snapshot_name):
                self.__logger.debug('snapshot found: {}'.format(item))
                return(item.snapshot)

            if item.childSnapshotList != []:
                return self.__single_snapshot_search(item.childSnapshotList, snapshot_name)

    def search_for_snapshot(self, vm, snapshot_name):
        for item in vm.snapshot.rootSnapshotList:
            if(item.name == snapshot_name):
                return(item.snapshot)

            if item.childSnapshotList != []:
                return self.__single_snapshot_search(item.childSnapshotList, snapshot_name)

        raise ValueError('snapshot {} cannot be found'.format(snapshot_name))
        return None

    def deploy(self, template, machine_name):
        self.__check_connection()

        destination_folder = None
        try:
            destination_folder = self.vm_folders.create_folder(settings.app['vsphere']['folder'])
        except:
            pass

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
                        destination_folder if destination_folder else item.parent,
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

    class VmFolders:

        def __init__(self, parent):
            self.vm_folders = {}
            self.__logger = logging.getLogger(__name__)
            self.parent=parent

        def create_subfolder(self, path, subpath):
            self.__logger.debug("A request to create {} in {}".format(subpath, path))
            objView = self.parent.content.viewManager.CreateContainerView(
                self.parent.content.rootFolder,
                [vim.Folder],
                True
            )
            new_folder = None
            for item in objView.view:
                if str(item) == self.vm_folders[path]:
                    new_folder = item.CreateFolder(name=subpath)
                    break

            objView.DestroyView()
            self.__collect_all_folders()
            return new_folder
        def __obtain_folder(self, path):
            objView = self.parent.content.viewManager.CreateContainerView(
                self.parent.content.rootFolder,
                [vim.Folder],
                True
            )
            try:
                for item in objView.view:
                    if str(item) == self.vm_folders[path]:
                        return item
            finally:
                objView.DestroyView()

        def create_folder(self, o_path):
            self.__collect_all_folders()
            path = self.__correct_folder_format(o_path)
            if path in self.vm_folders:
                return self.__obtain_folder(path)

            created_folder = None
            items = path.split('/')
            for splitindex in range(2, len(items)):
                temp_path = '/'.join(items[:splitindex])
                next_folder = items[splitindex:][0]
                if temp_path+'/'+next_folder  not in self.vm_folders:
                    created_folder = self.create_subfolder(temp_path, next_folder)

            if path not in self.vm_folders:
                self.__logger.warn("Directory {} not created".format(path))
            return self.__obtain_folder(path)

        def move_vm_to_folder(self, vm_uuid, out_path):
            path = self.__correct_folder_format(out_path)
            if path not in self.vm_folders:
                self.create_folder(path)

            vm = self.parent.content.searchIndex.FindByUuid(None, vm_uuid, True)
            self.__move_vm_to_existing_folder(vm, path)

        def __collect_all_folders(self):
            objView = self.parent.content.viewManager.CreateContainerView(
                self.parent.content.rootFolder,
                [vim.Folder],
                True
            )

            self.__logger.debug("collecting all vm folders....")
            self.vm_folders = {}
            for item in objView.view:
                full_name = self.__retrieve_full_folder_path(item)
                self.vm_folders[full_name] = str(item)
            objView.DestroyView()

        def __move_vm_to_existing_folder(self, vm, existing_path):
            objView2 = self.parent.content.viewManager.CreateContainerView(
                self.parent.content.rootFolder,
                [vim.Folder],
                True
            )

            for item in objView2.view:
                if str(item) == self.vm_folders[existing_path]:
                    task = item.MoveIntoFolder_Task(list=[vm])
                    while (task.info.state == 'running' or task.info.state == 'queued'):
                        time.sleep(0.2)
            objView2.DestroyView()

        def __retrieve_full_folder_path(self, folder):
            if isinstance(folder.parent, vim.Folder):
                return "{}/{}".format(
                    self.__retrieve_full_folder_path(folder.parent),
                    folder.name
                )
            else:
                return "/{}".format(folder.name)

        def __correct_folder_format(self, folder):
            f_folder = re.sub("[/\s]*$","", folder)
            if not f_folder.startswith('/vm/'):
                raise Exception("correct folder definition must look like\
                 \"/vm/root_folder/subfolder..... not {}\"".format(f_folder))

            return f_folder



