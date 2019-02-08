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

    def __find_snapshot_by_name(self, snapshot_list, snapshot_name):
        for item in snapshot_list:
            if(item.name == snapshot_name):
                self.__logger.debug('snapshot found: {}'.format(item))
                return(item.snapshot)

            if item.childSnapshotList != []:
                return self.__find_snapshot_by_name(item.childSnapshotList, snapshot_name)

    def search_for_snapshot(self, vm, snapshot_name):
        for item in vm.snapshot.rootSnapshotList:
            if(item.name == snapshot_name):
                return(item.snapshot)

            if item.childSnapshotList != []:
                return self.__find_snapshot_by_name(item.childSnapshotList, snapshot_name)

        raise ValueError('snapshot {} cannot be found'.format(snapshot_name))
        return None

    def __search_machine_by_name(self, vm_name):
        objView = self.content.viewManager.CreateContainerView(self.content.rootFolder,
                                                               [vim.VirtualMachine],
                                                               True)

        vm = next((item for item in objView.view if item.name == vm_name), None)
        objView.Destroy()
        return vm

    def __clone_template(self, template, machine_name, destination_folder, snapshot_name):

        snap = self.search_for_snapshot(
                                                    template,
                                                    snapshot_name
                    )

        # for full clone, use 'moveAllDiskBackingsAndDisallowSharing'
        spec = vim.vm.CloneSpec(
                        location=vim.vm.RelocateSpec(
                            datastore=template.datastore[0],
                            diskMoveType='createNewChildDiskBacking',
                            host=template.runtime.host,
                            transform=vim.vm.RelocateSpec.Transformation.sparse
                        ),
                        powerOn=False,
                        snapshot=snap,
                        template=False,
                    )

        task = template.CloneVM_Task(
                        destination_folder if destination_folder else template.parent,
                        machine_name,
                        spec
                    )
        return task

    def deploy(self, template_name, machine_name, **kwargs):
        self.__check_connection()
        destination_folder_name = settings.app['vsphere']['folder']
        if 'inventory_folder' in kwargs and kwargs['inventory_folder'] is not None:
            inventory_folder = kwargs['inventory_folder']
            destination_folder_name = '{}/{}'.format(
                                                        settings.app['vsphere']['folder'],
                                                        inventory_folder
            )

        destination_folder = None
        try:
            destination_folder = self.vm_folders.create_folder(destination_folder_name)
        except Exception as e:
            self.__logger.warn(
                'destination folder {} was not created because {}'.format(
                    destination_folder_name,
                    e
                )
            )

            raise e

        template = self.__search_machine_by_name(template_name)
        vm = None
        if not template:
            raise RuntimeError("template {} hasn't been found".format(template_name))

        self.__logger.debug('template moid: {}\t name: {}'.format(template._GetMoId(),
                                                                  template.name))
        self.__logger.debug('parent: {}'.format(template.parent._GetMoId()))
        self.__logger.debug('datastore: {}'.format(template.datastore[0].name))
        self.__logger.debug('snapshot: {}'.format(template.snapshot.currentSnapshot))
        retry_deploy_count = settings.app['vsphere']['retries']['deploy']
        retry_delete_count = settings.app['vsphere']['retries']['delete']
        for i in range(retry_deploy_count):
            try:
                task = self.__clone_template(
                    template,
                    machine_name,
                    destination_folder,
                    settings.app['vsphere']['default_snapshot_name']
                )

                vm = self.wait_for_task(task)
                self.__logger.debug('Task finished with value: {}'.format(vm))
                if not vm:
                    # machine must be checked whether it has been created or not,
                    # in no-case machine creation must be re-executed
                    # in yes-case created machine must be deleted and no-case repeated
                    for f in range(retry_delete_count):
                        failed_vm = self.__search_machine_by_name(machine_name)
                        if failed_vm:
                            self.__logger.warn(
                                'junk machine {} has been created: {}'.format(
                                    machine_name,
                                    failed_vm
                                )
                            )
                            destroy_task = failed_vm.Destroy_Task()
                            self.wait_for_task(destroy_task)
                            failed_vm_recheck = self.__search_machine_by_name(machine_name)
                            if not failed_vm_recheck:
                                self.__logger.warn(
                                    'junk machine {} has been deleted successfully'.format(
                                        machine_name
                                    )
                                )
                                break
                            else:
                                self.__logger.warn(
                                    'junk machine {} has not been deleted'.format(
                                        machine_name
                                    )
                                )
                    time.sleep(1)
                else:
                    self.__logger.debug('vms parent: {}'.format(vm.parent))
            except Exception as e:
                self.__logger.warn('pyvmomi related exception: ', exc_info=True)
            if vm:
                return vm.config.uuid
        raise RuntimeError("virtual machine hasn't been deployed")

    def __search_sibling_machines(self, parent_folder, vm_uuid):
        result = []
        self.__logger.debug('searching for sibling machines in: {}({})'.format(
                                                                                parent_folder,
                                                                                parent_folder.name
        ))
        objView = self.content.viewManager.CreateContainerView(
                                                                self.content.rootFolder,
                                                                [vim.VirtualMachine],
                                                                True
        )

        for item in objView.view:
            if item.parent == parent_folder and item.config.uuid != vm_uuid:
                self.__logger.debug('>>found: {}'.format(item.name))
                result.append(item)
        objView.Destroy()
        self.__logger.debug('searching done')
        return result

    def undeploy(self, uuid):
        self.__check_connection()

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)
        if vm:
            self.__logger.debug('found vm: {}'.format(vm.config.uuid))

            parent_folder = vm.parent
            sibling_machines = self.__search_sibling_machines(parent_folder, vm.config.uuid)

            task = vm.Destroy_Task()
            self.wait_for_task(task)
            self.__logger.debug('vm killed')

            if len(sibling_machines) == 0:
                self.__logger.debug(
                    'folder: {}({}) is going to be removed'.format(
                                                                    parent_folder,
                                                                    parent_folder.name
                    )
                )
                self.vm_folders.delete_folder(parent_folder)
                self.__logger.debug('folder: deleted')
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
            self.parent = parent

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

        def create_folder(self, folder_path):
            self.__collect_all_folders()
            path = self.__correct_folder_format(folder_path)
            if path in self.vm_folders:
                return self.__obtain_folder(path)

            created_folder = None
            items = path.split('/')
            for splitindex in range(2, len(items)):
                temp_path = '/'.join(items[:splitindex])
                next_folder = items[splitindex:][0]
                if temp_path+'/'+next_folder not in self.vm_folders:
                    created_folder = self.create_subfolder(temp_path, next_folder)

            if path not in self.vm_folders:
                self.__logger.warn("Directory {} not created".format(path))
            return self.__obtain_folder(path)

        def delete_folder(self, folder):
            task = folder.Destroy_Task()
            self.parent.wait_for_task(task)

        def move_vm_to_folder(self, vm_uuid, folder_path):
            path = self.__correct_folder_format(folder_path)
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
            f_folder = re.sub(r'[/\s]*$', '', folder)
            if not f_folder.startswith('/vm/'):
                raise Exception("correct folder definition must look like\
                 \"/vm/root_folder/subfolder..... not {}\"".format(f_folder))

            return f_folder
