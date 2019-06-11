from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl

from web.settings import Settings as settings

import sys
import ssl
import atexit
import time
import logging
import re
import random


class VCenter():

    def __init__(self):
        self._connected = False
        self.content = None
        self.__logger = logging.getLogger(__name__)
        self.vm_folders = None

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
        self.vm_folders = VCenter.VmFolders(self)
        self.destination_datastore = None
        self.refresh_destination_datastore()
        self.refresh_destination_resource_pool()

    def idle(self):
        self.__check_connection()
        self.__logger.debug('keeping connection alive: {}'.format(self.content.about.vendor))

    def refresh_destination_datastore(self):
        self.destination_datastore = self.__get_destination_datastore()

    def refresh_destination_resource_pool(self):
        self.destination_resource_pool = self.__get_destination_resource_pool()

    def __get_destination_datastore(self):
        self.__logger.debug('Getting destination datastores...')
        try:
            objView = self.content.viewManager.CreateContainerView(
                                                                       self.content.rootFolder,
                                                                       [vim.StoragePod],
                                                                       True
                )

            wanted_name = settings.app['vsphere']['storage']
            sp = next((item for item in objView.view if item.name == wanted_name), None)
            if sp:
                self.__logger.debug('found datastore cluster: {} {}'.format(sp.name, sp))
                freespace = 0
                output_ds = None
                for ds in sp.childEntity:
                    ds_freespace = ds.summary.freeSpace/1024/1024/1024
                    self.__logger.debug(
                        'inspected datastore: {}, {:.2f} GiB left'.format(ds.name, ds_freespace)
                    )
                    if ds.summary.accessible and ds_freespace > freespace:
                        freespace = ds_freespace
                        output_ds = ds
                self.__logger.debug(
                    'selected datastore: {}, {:.2f} GiB left'.format(output_ds.name, freespace)
                )
                self.__logger.debug('Getting done')
                return output_ds

        except vmodl.fault.ManagedObjectNotFound:
            self.__logger.warn('vmodl.fault.ManagedObjectNotFound has occured')
        except Exception:
            settings.raven.captureException(exc_info=True)
        finally:
            objView.Destroy()

        # search for datastore name
        try:
            objView = self.content.viewManager.CreateContainerView(
                                                                       self.content.rootFolder,
                                                                       [vim.Datastore],
                                                                       True
                )

            wanted_name = settings.app['vsphere']['storage']
            sp = next((item for item in objView.view if item.name == wanted_name), None)
            if sp and sp.summary.accessible:
                self.__logger.debug(
                    'selected datastore: {}, {:.2f} GiB left'.format(
                        sp.name,
                        sp.summary.freeSpace/1024/1024/1024
                    )
                )
                return sp
            return None

        except vmodl.fault.ManagedObjectNotFound:
            self.__logger.warn('vmodl.fault.ManagedObjectNotFound has occured')
        except Exception:
            settings.raven.captureException(exc_info=True)
        finally:
            objView.Destroy()
            self.__logger.debug('Getting done')

    def __get_destination_resource_pool(self):
        self.__logger.debug('Getting destination resource pool...')
        try:
            objView = self.content.viewManager.CreateContainerView(
                                                                       self.content.rootFolder,
                                                                       [vim.ResourcePool],
                                                                       True
                )

            wanted_name = settings.app['vsphere']['resource_pool']
            sp = next((item for item in objView.view if item.name == wanted_name), None)
            if sp:
                self.__logger.debug('found resource pool: {} {}'.format(sp.name, sp))
                return sp

        except vmodl.fault.ManagedObjectNotFound:
            self.__logger.warn('vmodl.fault.ManagedObjectNotFound has occured')
        except Exception:
            settings.raven.captureException(exc_info=True)
        finally:
            objView.Destroy()
            self.__logger.debug('Getting done')

        return None

    def __sleep_between_tries(self):
        time.sleep(random.uniform(
                        settings.app['vsphere']['retries']['delay_period_min'],
                        settings.app['vsphere']['retries']['delay_period_max']
        )
        )

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
        for cnt in range(settings.app['vsphere']['retries']['default']):
            try:
                objView = self.content.viewManager.CreateContainerView(
                                                                       self.content.rootFolder,
                                                                       [vim.VirtualMachine],
                                                                       True
                )

                vm = next((item for item in objView.view if item.name == vm_name), None)
                objView.Destroy()
                return vm
            except vmodl.fault.ManagedObjectNotFound:
                self.__logger.warn(
                                    'vmodl.fault.ManagedObjectNotFound nas occured, try: {}'.format(
                                        cnt
                                    )
                )
                self.__sleep_between_tries()
            except Exception:
                settings.raven.captureException(exc_info=True)
        raise ValueError('machine {} cannot be found'.format(vm_name))

    def __clone_template(self, template, machine_name, destination_folder, snapshot_name):

        snap = self.search_for_snapshot(
                                                    template,
                                                    snapshot_name
                    )

        sys_dest_ds = self.destination_datastore
        dest_datastore = template.datastore[0] if sys_dest_ds is None else sys_dest_ds

        # for full clone, use 'moveAllDiskBackingsAndDisallowSharing'
        if self.destination_resource_pool:
            relocate_spec = vim.vm.RelocateSpec(
                datastore=dest_datastore,
                diskMoveType='createNewChildDiskBacking',
                pool=self.destination_resource_pool,
                transform=vim.vm.RelocateSpec.Transformation.sparse
            )
        else:
            relocate_spec = vim.vm.RelocateSpec(
                datastore=dest_datastore,
                diskMoveType='createNewChildDiskBacking',
                host=template.runtime.host,
                transform=vim.vm.RelocateSpec.Transformation.sparse
            )
        spec = vim.vm.CloneSpec(
                        location=relocate_spec,
                        powerOn=False,
                        snapshot=snap,
                        template=False,
                    )

        task = template.CloneVM_Task(
                        destination_folder,
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
        retry_deploy_count = settings.app['vsphere']['retries']['deploy']
        retry_delete_count = settings.app['vsphere']['retries']['delete']
        vm = None
        vm_uuid = None
        for i in range(retry_deploy_count):
            try:
                template = self.__search_machine_by_name(template_name)
                if not template:
                    raise RuntimeError("template {} hasn't been found".format(template_name))

                self.__logger.debug('template moid: {}\t name: {}'.format(template._GetMoId(),
                                                                          template.name))
                self.__logger.debug('parent: {}'.format(template.parent._GetMoId()))
                self.__logger.debug('datastore: {}'.format(template.datastore[0].name))
                self.__logger.debug('snapshot: {}'.format(template.snapshot.currentSnapshot))
                task = self.__clone_template(
                    template,
                    machine_name,
                    self.vm_folders.create_folder(settings.app['vsphere']['folder']),
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
                    self.__sleep_between_tries()
                else:
                    self.__logger.debug('vms parent: {}'.format(vm.parent))
                    vm_uuid = vm.config.uuid
            except Exception as e:
                settings.raven.captureException(exc_info=True)
                self.__logger.warn('pyvmomi related exception: ', exc_info=True)
                self.__sleep_between_tries()
            if vm:
                for i in range(retry_deploy_count):
                    try:
                        self.vm_folders.move_vm_to_folder(vm_uuid, destination_folder_name)
                    except vim.fault.DuplicateName as e:
                        settings.raven.captureException(exc_info=True)
                        self.__logger.warn(
                            'destination folder {} not created because; trying again'.format(
                                destination_folder_name
                            )
                        )
                    except Exception as e:
                        settings.raven.captureException(exc_info=True)
                        self.__logger.warn(
                            'destination folder {} was not created because {}'.format(
                                destination_folder_name,
                                e
                            )
                        )
                        self.__sleep_between_tries()
                        raise e

                return vm_uuid
        raise RuntimeError("virtual machine hasn't been deployed")

    def __has_sibling_objects(self, parent_folder, vm_uuid):
        self.__logger.debug('are there sibling machines in: {}({})?'.format(
                                                                                parent_folder,
                                                                                parent_folder.name
        ))
        for rep in range(5):
            try:
                objView = self.content.viewManager.CreateContainerView(
                                                                self.content.rootFolder,
                                                                [vim.VirtualMachine, vim.Folder],
                                                                True
                )

                for item in objView.view:
                    if item.parent == parent_folder:
                        if isinstance(item, vim.Folder):
                            self.__logger.debug('>>found folder: {}'.format(item.name))
                            return True
                        if item.config.uuid != vm_uuid:
                            self.__logger.debug('>>found vm: {}'.format(item.name))
                            return True
                return False
            except vmodl.fault.ManagedObjectNotFound:
                self.__sleep_between_tries()
                pass
            except Exception:
                settings.raven.captureException(exc_info=True)
                self.__sleep_between_tries()
            finally:
                self.__logger.debug('searching done')
                objView.Destroy()
        return True

    def undeploy(self, uuid):
        self.__check_connection()
        for attempt in range(6):
            try:
                vm = self.content.searchIndex.FindByUuid(None, uuid, True)
                if vm:
                    self.__logger.debug('found vm: {}'.format(vm.config.uuid))

                    parent_folder = vm.parent
                    parent_folder_name = vm.parent.name
                    has_sibling_machines = True
                    # has_sibling_machines = self.__has_sibling_objects(
                    #    has_sibling_machines = True
                    #    parent_folder,
                    #    vm.config.uuid
                    # )

                    for i in range(5):
                        try:
                            task = vm.Destroy_Task()
                            self.wait_for_task(task)
                            self.__logger.debug('vm killed {}'.format(i))
                            break
                        except vmodl.fault.ManagedObjectNotFound:
                            self.__sleep_between_tries()

                    if not has_sibling_machines:
                        self.__logger.debug(
                            'folder: {} is going to be removed'.format(
                                                                    parent_folder_name
                            )
                        )
                        self.vm_folders.delete_folder(parent_folder)
                        self.__logger.debug('folder: {} has been deleted'.format(
                            parent_folder_name
                        )
                        )
                    return
                else:
                    self.__logger.warn(
                        'machine {} not found or has been already deleted'.format(uuid)
                    )
                    return
            except vmodl.fault.ManagedObjectNotFound:
                self.__logger.warn('problem while undeploying machine {}'.format(uuid))
                self.__sleep_between_tries()
            except Exception:
                settings.raven.captureException(exc_info=True)
                self.__sleep_between_tries()

        raise RuntimeError("virtual machine hasn't been undeployed")

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
        for i in range(settings.app['vsphere']['retries']['config_network']):
            try:
                vm = self.content.searchIndex.FindByUuid(None, uuid, True)
                if vm:
                    self.__logger.debug('found vm: {}'.format(uuid))
                    task = vm.PowerOffVM_Task()
                    self.wait_for_task(task)
                    self.__logger.debug('vm powered off')
                    return
                else:
                    raise Exception('machine {} not found'.format(uuid))
            except Exception:
                settings.raven.captureException(exc_info=True)
                self.__sleep_between_tries()

    def config_network(self, uuid, **kwargs):
        self.__logger.debug('config_network')
        self.__check_connection()
        for i in range(settings.app['vsphere']['retries']['config_network']):
            try:

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
                break
            except Exception:
                self.__sleep_between_tries()

    def _get_machine_nos_id(self, vm, uuid):
        result = ''
        try:
            for hw in vm.config.hardware.device:
                try:
                    mac = hw.macAddress
                    result = "v{}".format(re.sub(':', '', str(mac).upper()))
                except AttributeError:
                    pass
        except Exception:
            self.__logger.debug("obtaining nos_id on machine {} failed".format(uuid), exc_info=True)
        finally:
            return result

    def _get_machine_ips(self, vm, uuid):
        result = []
        try:
            for adapter in vm.guest.net:
                for ip in adapter.ipConfig.ipAddress:
                    result.append(ip.ipAddress)
        except Exception:
            self.__logger.debug("obtaining ips on machine {} failed".format(uuid), exc_info=True)
        finally:
            return result

    def _get_machine_name(self, vm, uuid):
        result = "unknown"
        for i in range(settings.app['vsphere']['retries']['default']):
            try:
                result = vm.config.name
            except Exception:
                self.__logger.debug("obtaining machine name {} failed".format(uuid), exc_info=True)
        return result

    def get_machine_info(self, uuid):
        self.__check_connection()
        result = {'ip_addresses': [], 'nos_id': ''}

        vm = self.content.searchIndex.FindByUuid(None, uuid, True)
        try:
            if vm:
                self.__logger.debug('found vm: {}'.format(uuid))
                result['ip_addresses'] = self._get_machine_ips(vm, uuid)
                result['nos_id'] = self._get_machine_nos_id(vm, uuid)
                result['machine_name'] = self._get_machine_name(vm, uuid)
                self.__logger.debug('get machine info end')
        except Exception:
            self.__logger.debug('get machine info on {} failed'.format(uuid), exc_info=True)
        finally:
            return result

    def wait_for_task(self, task):
        while (task.info.state == 'running' or task.info.state == 'queued'):
            message = "no-message"
            progress = "n/a"
            try:
                progress = task.info.progress
                message = task.info.description.message
            except Exception:
                self.__logger.warn('Problem obtaining progress or description on a vsphere task')

            self.__logger.debug('Progress {}% | Task: {}\r'.format(
                progress,
                message
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
            # this stores all folders in vsphere at the time the class was instantiated
            self.vm_folders = {}
            # this stores all subfolders where this lm unit operates
            self.system_folders = {}

            self.__logger = logging.getLogger(__name__)
            self.parent = parent
            self.__collect_all_folders()

        def __sleep_between_tries(self):
            time.sleep(random.uniform(
                            settings.app['vsphere']['retries']['delay_period_min'],
                            settings.app['vsphere']['retries']['delay_period_max']
            )
            )

        def __get_system_root_folder(self):
            if not settings.app['vsphere']['folder'] in self.vm_folders:
                self.__logger.warn('{} not in vm_folders'.format(settings.app['vsphere']['folder']))
                # self.__logger.warn('{}'.format(self.vm_folders.keys()))
            folder = self.vm_folders[settings.app['vsphere']['folder']]
            # self.__logger.debug('folder: {}'.format(folder))

            objView = self.parent.content.viewManager.CreateContainerView(
                self.parent.content.rootFolder,
                [vim.Folder],
                True
            )

            try:
                for item in objView.view:
                    if str(item) == folder:
                        return item
                raise Exception("root folder not obtained")
            finally:
                objView.DestroyView()

        def create_subfolder(self, path, subpath):
            self.__logger.debug("A request to create {} in {}".format(subpath, path))
            objView = self.parent.content.viewManager.CreateContainerView(
                # we have to start from parent to fing the current root folder
                self.__get_system_root_folder().parent,
                [vim.Folder],
                True
            )

            new_folder = None
            for item in objView.view:
                if str(item) == self.system_folders[path]:
                    self.__logger.debug('parent folder {} found'.format(path))
                    try:
                        new_folder = item.CreateFolder(name=subpath)
                        break
                    except vim.fault.DuplicateName:
                        self.__sleep_between_tries()
                        break

            objView.DestroyView()
            self.__logger.debug("creation done.")
            self.__collect_system_folders()
            return new_folder

        def __obtain_folder(self, path):
            objView = self.parent.content.viewManager.CreateContainerView(
                self.__get_system_root_folder().parent,
                [vim.Folder],
                True
            )
            try:
                for item in objView.view:
                    if path in self.system_folders and str(item) == self.system_folders[path]:
                        return item
            finally:
                objView.DestroyView()

            self.__logger.warn("folder: {} not found".format(path))

        def create_folder(self, folder_path):
            self.__collect_system_folders()
            path = self.__correct_folder_format(folder_path)
            if path in self.system_folders:
                return self.__obtain_folder(path)

            created_folder = None
            items = path.split('/')
            for splitindex in range(2, len(items)):
                temp_path = '/'.join(items[:splitindex])
                next_folder = items[splitindex:][0]
                if temp_path+'/'+next_folder not in self.system_folders:
                    created_folder = self.create_subfolder(temp_path, next_folder)
                else:
                    self.__logger.debug('{} exists'.format(temp_path+'/'+next_folder))

            if path not in self.system_folders:
                self.__logger.warn("Directory {} not created".format(path))
            return self.__obtain_folder(path)

        def delete_folder(self, folder):
            task = folder.Destroy_Task()
            self.parent.wait_for_task(task)

        def move_vm_to_folder(self, vm_uuid, folder_path):
            path = self.__correct_folder_format(folder_path)
            if path not in self.system_folders:
                self.create_folder(path)

            vm = self.parent.content.searchIndex.FindByUuid(None, vm_uuid, True)
            self.__move_vm_to_existing_folder(vm, path)

        def __collect_system_folders(self):
            for repetition in range(5):
                try:
                    root_folder_moref = self.__get_system_root_folder()
                    objView = self.parent.content.viewManager.CreateContainerView(
                        root_folder_moref,
                        [vim.Folder],
                        True
                    )

                    self.__logger.debug("collecting system vm folders....")
                    self.__logger.debug("\troot_folder_moref: {}".format(str(root_folder_moref)))
                    self.system_folders = {
                        settings.app['vsphere']['folder']: str(root_folder_moref)
                    }
                    # all parent folders must be initially added as well
                    for i in self.vm_folders.keys():
                        if settings.app['vsphere']['folder'].startswith(i):
                            self.system_folders[i] = self.vm_folders[i]

                    for item in objView.view:
                        full_name = self.__retrieve_full_folder_path(item)
                        self.system_folders[full_name] = str(item)

                    return
                except vmodl.fault.ManagedObjectNotFound as e:
                    self.__logger.warn(
                        "collect_system_folders errored atempt: {}".format(repetition)
                    )
                    self.__sleep_between_tries()
                except Exception as e:
                    settings.raven.captureException(exc_info=True)
                    self.__logger.error(
                        "collect_system_folders errored atempt: {}".format(repetition)
                    )
                    raise e
                finally:
                    objView.DestroyView()

        def __collect_all_folders(self):
            for repetition in range(5):
                try:

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
                    self.__logger.debug("collecting done.")
                    return
                except vmodl.fault.ManagedObjectNotFound as e:
                    self.__logger.warn("collect_all_folders errored atempt: {}".format(repetition))
                    self.__sleep_between_tries()
                except Exception as e:
                    settings.raven.captureException(exc_info=True)
                    self.__logger.error("collect_all_folders errored atempt: {}".format(repetition))
                    raise e
                finally:
                    objView.DestroyView()

        def __move_vm_to_existing_folder(self, vm, existing_path):
            objView2 = self.parent.content.viewManager.CreateContainerView(
                self.__get_system_root_folder(),
                [vim.Folder],
                True
            )
            for item in objView2.view:
                if str(item) == self.system_folders[existing_path]:
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
