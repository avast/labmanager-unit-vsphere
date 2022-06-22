import base64
import enum
import logging
import re
import random
import requests
import ssl
import time
import uuid
import urllib.request

from typing import Union, Optional

from pyVim.connect import SmartConnect
from pyVmomi import vim, vmodl
from web.settings import Settings


class CloneApproach(enum.Enum):
    LINKED_CLONE = 'linked_clone'
    INSTANT_CLONE = 'instant_clone'


class VCenter:

    def __init__(self):
        self._connected = False
        self._connection_cookie = None
        self.content = None
        self.__logger = logging.getLogger(__name__)
        self.vm_folders = None
        self.destination_datastore = None
        self.destination_resource_pool = None

    def __check_connection(self):
        result = self.__get_objects_list_from_container(self.content.rootFolder, vim.Datastore)
        if not result:
            self.connect()

    def connect(self):
        context = ssl._create_unverified_context()

        si = SmartConnect(
                            host=Settings.app['vsphere']['host'],
                            user=Settings.app['vsphere']['username'],
                            pwd=Settings.app['vsphere']['password'],
                            port=Settings.app['vsphere']['port'],
                            connectionPoolTimeout=Settings.app['vsphere']['timeout'],
                            sslContext=context
        )

        if not si:
            self.__logger.error(
                'Cannot connect to specified host using specified username and password'
            )

        self.content = si.content
        self._connection_cookie = si._stub.cookie
        self._connected = True
        self.vm_folders = VCenter.VmFolders(self)
        self.refresh_destination_datastore()
        self.refresh_destination_resource_pool()

    def idle(self):
        self.__check_connection()
        self.__logger.debug('keeping connection alive: {}'.format(self.content.about.vendor))

    def refresh_destination_datastore(self):
        self.destination_datastore = self.__get_destination_datastore()

    def refresh_destination_resource_pool(self):
        self.destination_resource_pool = self.__get_destination_resource_pool()

    def __find_datastore_cluster_by_name(self, datastore_cluster_name):
        """
        Returns datastore cluster, if datastore cluster with this name exists, otherwise None.
        :param datastore_cluster_name:
        :return: datastore cluster or None
        """
        data_clusters = self.__get_objects_list_from_container(self.content.rootFolder, vim.StoragePod)
        for dc in data_clusters:
            if dc.name == datastore_cluster_name:
                return dc

        return None

    def __find_datastore_by_name(self, datastore_name):
        """
        Returns datastore, if datastore with this name exists, otherwise None.
        :param datastore_name:
        :return: datastore or None
        """
        data_stores = self.__get_objects_list_from_container(self.content.rootFolder, vim.Datastore)
        for ds in data_stores:
            if ds.name == datastore_name:
                return ds
        return None

    def __get_free_datastore(self, datastore_cluster):
        """
        Returns datastore from 'datastore_cluster' with most free space
        :param datastore_cluster:
        :return: datastore
        """
        free_space = 0
        output_ds = None
        for ds in datastore_cluster.childEntity:
            datastore_free_space = round(ds.summary.freeSpace/1024/1024/1024, 2)
            self.__logger.debug(
                'inspected datastore: {}, {:.2f} GiB left'.format(ds.name, datastore_free_space)
            )
            if ds.summary.accessible and datastore_free_space > free_space:
                free_space = datastore_free_space
                output_ds = ds

        if output_ds is not None:
            self.__logger.debug(f'selected datastore: {output_ds.name}, {free_space} GiB left')

        return output_ds

    def __get_destination_datastore(self):
        self.__logger.debug('Getting destination datastores...')

        unit_datastore_cluster_name = Settings.app['vsphere']['storage']
        ds_cluster = self.__find_datastore_cluster_by_name(unit_datastore_cluster_name)

        if ds_cluster is not None:
            self.__logger.debug(f'found datastore cluster: {ds_cluster.name} ({ds_cluster})')
            datastore = self.__get_free_datastore(ds_cluster)
            return datastore

        # 'vsphere.storage' may contain directly datastore name
        datastore_name = unit_datastore_cluster_name
        datastore = self.__find_datastore_by_name(datastore_name)

        if datastore is not None and datastore.summary.accessible:
            ds_free_space = round(datastore.summary.freeSpace/1024/1024/1024, 2)
            self.__logger.debug(f'selected datastore: {datastore.name}, {ds_free_space} GiB left')

        return datastore

    def __get_destination_resource_pool(self):
        self.__logger.debug('Getting destination resource pool...')
        resource_pool_name = Settings.app['vsphere']['resource_pool']
        resource_pools = self.__get_objects_list_from_container(self.content.rootFolder, vim.ResourcePool)
        for rp in resource_pools:
            if rp.name == resource_pool_name:
                return rp
        return None

    @staticmethod
    def __sleep_between_tries():
        time.sleep(random.uniform(
                        Settings.app['vsphere']['retries']['delay_period_min'],
                        Settings.app['vsphere']['retries']['delay_period_max']
        )
        )

    def __find_snapshot_by_name(self, snapshot_list, snapshot_name):
        for item in snapshot_list:
            if item.name == snapshot_name:
                self.__logger.debug('snapshot found: {}'.format(item))
                return item.snapshot

            if item.childSnapshotList:
                res_snap = self.__find_snapshot_by_name(item.childSnapshotList, snapshot_name)
                if res_snap:
                    return res_snap

        return None

    def search_for_snapshot(self, vm, snapshot_name):
        res_snap = self.__find_snapshot_by_name(vm.snapshot.rootSnapshotList, snapshot_name)
        if res_snap is None:
            raise ValueError('snapshot {} cannot be found'.format(snapshot_name))

        return res_snap

    def __determine_root_system_folder(self, dc_folder):
        """
            if root_system_folder is specified this tries to search for it and speeds up the deployment
        """
        root_system_folder_name = Settings.app['vsphere']['root_system_folder']
        if root_system_folder_name is not None:
            root_system_folder = next(
                (item for item in dc_folder.vmFolder.childEntity if item.name == root_system_folder_name),
                dc_folder
            )
            if dc_folder == root_system_folder:
                self.__logger.warning("root system folder: {} cannot be found; cfg: {}".format(
                    root_system_folder_name,
                    "config->vsphere->root_system_folder"
                ))
            return root_system_folder
        return dc_folder

    def __determine_dc_folder(self, root_folder):
        """
            Determines whether specific datacenter may be used to search for machines
            if search is not successful it returns the origin
            if search is successful it tries to locate the root folder of the system
        """
        datacenter_name = Settings.app['vsphere']['datacenter']
        if datacenter_name is not None:
            dc_folder = next(
                (item for item in root_folder.childEntity if item.name == datacenter_name),
                root_folder
            )
            return self.__determine_root_system_folder(dc_folder)
        return root_folder

    def __search_machine_by_name(self, vm_name):
        for cnt in range(Settings.app['vsphere']['retries']['default']):
            try:
                container_view = self.content.viewManager.CreateContainerView(
                                                                       self.__determine_dc_folder(
                                                                           self.content.rootFolder,
                                                                       ),
                                                                       [vim.VirtualMachine],
                                                                       True
                )

                vm = next((item for item in container_view.view if item.name == vm_name), None)
                container_view.Destroy()
                return vm
            except vmodl.fault.ManagedObjectNotFound:
                self.__logger.warning(
                                    'vmodl.fault.ManagedObjectNotFound nas occurred, try: {}'.format(
                                        cnt
                                    )
                )
                self.__sleep_between_tries()
            except Exception:
                Settings.raven.captureException(exc_info=True)
        raise ValueError('machine {} cannot be found'.format(vm_name))

    def __get_linked_clone_task(self, template, machine_name, destination_folder, snapshot_name):

        snap = self.search_for_snapshot(template, snapshot_name)

        picked_dest_ds = template.datastore[0] if self.destination_datastore is None else self.destination_datastore

        # for full clone, use 'moveAllDiskBackingsAndDisallowSharing'
        if self.destination_resource_pool:
            relocate_spec = vim.vm.RelocateSpec(
                datastore=picked_dest_ds,
                diskMoveType='createNewChildDiskBacking',
                pool=self.destination_resource_pool,
                transform=vim.vm.RelocateSpec.Transformation.sparse
            )
        else:
            relocate_spec = vim.vm.RelocateSpec(
                datastore=picked_dest_ds,
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

    def __get_instant_clone_task(self, source_machine, destination_machine_name, destination_folder):
        """
        Creates task for performing an instant clone from existing source machine
        :param source_machine: machine to base new machine on
        :param destination_machine_name: name of newly created machine
        :param destination_folder: location of the machine
        :return: task
        """
        src_machine_state = source_machine.runtime.powerState
        is_instant_clone_frozen = source_machine.runtime.instantCloneFrozen
        if src_machine_state != 'poweredOn':
            raise RuntimeError(f'Machine {repr(source_machine.name)} must be \'running\' to perform instant clone, '
                               f'but was {repr(src_machine_state)}')
        if is_instant_clone_frozen is not True:
            raise RuntimeError(f'Machine {repr(source_machine.name)} must be \'frozen\' to perform instant clone, '
                               f'but \'instantCloneFrozen\' property was \'{(is_instant_clone_frozen)}\'')
        relocate_spec = vim.vm.RelocateSpec()
        relocate_spec.folder = destination_folder
        relocate_spec.pool = self.destination_resource_pool
        instant_clone_spec = vim.vm.InstantCloneSpec(name=destination_machine_name, location=relocate_spec)

        return source_machine.InstantClone_Task(spec=instant_clone_spec)

    def __get_clone_task(self,
                         clone_approach: CloneApproach,
                         template: vim.VirtualMachine,
                         target_machine_name: str,
                         machine_folder: str,
                         default_snap_name: str):

        if clone_approach is CloneApproach.LINKED_CLONE:
            task = self.__get_linked_clone_task(template, target_machine_name, machine_folder, default_snap_name)

        elif clone_approach is CloneApproach.INSTANT_CLONE:
            task = self.__get_instant_clone_task(template, target_machine_name, machine_folder)
        else:
            raise ValueError(f'Invalid clone_approach value: {clone_approach}')

        return task

    def clone_vm(self, template_name: str, machine_name: str, clone_approach: CloneApproach) -> Optional[vim.VirtualMachine]:
        """
        Clones VM specified by template_name to target VM specified by machine_name
        :param template_name: source machine name
        :param machine_name:  target machine name
        :param clone_approach: clone strategy (instant or linked)
        :return: VM object if successful, else None
        """
        template = self.__search_machine_by_name(template_name)
        if not template:
            raise RuntimeError(f"template {template_name} hasn't been found")

        self.__logger.debug(f'template moid: {template._GetMoId()}\t name: {template.name}')
        self.__logger.debug(f'parent: {template.parent._GetMoId()}')
        self.__logger.debug(f'datastore: {template.datastore[0].name}')
        if template.snapshot:
            self.__logger.debug(f'snapshot: {template.snapshot.currentSnapshot}')

        machine_folder = self.vm_folders.create_folder(Settings.app['vsphere']['folder'])
        default_snap_name = Settings.app['vsphere']['default_snapshot_name']

        task = self.__get_clone_task(clone_approach, template, machine_name, machine_folder, default_snap_name)
        vm = self.wait_for_task(task)
        self.__logger.debug(f'{clone_approach} task finished with result: {vm}')

        if vm and clone_approach is CloneApproach.INSTANT_CLONE:
            # perform the restart of the network for instant clone
            login_username = Settings.app.get('vms', {}).get('login_username', None)
            login_password = Settings.app.get('vms', {}).get('login_password', None)

            post_install_clone_command_list = Settings.app['vsphere'].get('instant_clone_post_commands', [])
            self.__logger.debug(f'Post instant clone commands in config: {len(post_install_clone_command_list)}')

            for command_dict in post_install_clone_command_list:
                os = command_dict.get('os', '')
                description = command_dict.get('description', 'N/A')
                command = command_dict.get('command')
                args = command_dict.get('args', '')
                username = command_dict.get('username', login_username)
                password = command_dict.get('password', login_password)

                # execute only if template matches os
                if not template_name.startswith(os):
                    self.__logger.debug(f'Skipping task with os={os} for {template_name}')
                    continue

                # check if command and credentials are supplied
                if not all([command, username, password]):
                    pass_msg = '<empty>' if not password else '*' * len(password)
                    self.__logger.warning(f'Incomplete task definition; command={command}, args={args}'
                                          f'username={username}, password={pass_msg}, cannot run \'{description}\'!')
                    continue

                # run post instant clone commands
                self.__logger.debug(f'Running \'{description}\' in VM {vm.config.uuid}')
                exit_code = self.run_process_in_vm(machine_uuid=vm.config.uuid,
                                                   username=username,
                                                   password=password,
                                                   program_path=command,
                                                   program_arguments=args)

                result = 'succeeded' if exit_code == 0 else 'failed'
                self.__logger.debug(f'\'{description}\' {result} in {vm.config.uuid}')

        return vm

    def get_machine_by_uuid(self, machine_uuid):
        self.__logger.debug(f'-> get_machine_by_uuid({machine_uuid})')
        self.__check_connection()
        vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
        if vm is None:
            raise Exception(f'machine {machine_uuid} not found')

        self.__logger.debug(f'<- get_machine_by_uuid: {vm}')
        return vm

    def deploy(self, template_name, machine_name, running, **kwargs):
        self.__check_connection()
        destination_folder_name = Settings.app['vsphere']['folder']
        if 'inventory_folder' in kwargs and kwargs['inventory_folder'] is not None:
            inventory_folder = kwargs['inventory_folder']
            destination_folder_name = '{}/{}'.format(
                                                        Settings.app['vsphere']['folder'],
                                                        inventory_folder
            )
        retry_deploy_count = Settings.app['vsphere']['retries']['deploy']
        retry_delete_count = Settings.app['vsphere']['retries']['delete']
        inst_clone_enabled = Settings.app['vsphere']['instant_clone_enabled']

        clone_approach = CloneApproach.INSTANT_CLONE if inst_clone_enabled and running else CloneApproach.LINKED_CLONE
        self.__logger.debug(f'Using {clone_approach} (running={running}, instant_clone_enabled={inst_clone_enabled})')

        vm = None
        vm_uuid = None

        for i in range(retry_deploy_count):
            try:
                # clone VM based on specified approach
                vm = self.clone_vm(template_name, machine_name, clone_approach)

                if not vm:
                    # machine must be checked whether it has been created or not,
                    # in no-case machine creation must be re-executed
                    # in yes-case created machine must be deleted and no-case repeated
                    for f in range(retry_delete_count):
                        failed_vm = self.__search_machine_by_name(machine_name)
                        if failed_vm:
                            self.__logger.warning(
                                'junk machine {} has been created: {}'.format(
                                    machine_name,
                                    failed_vm
                                )
                            )
                            destroy_task = failed_vm.Destroy_Task()
                            self.wait_for_task(destroy_task)
                            failed_vm_recheck = self.__search_machine_by_name(machine_name)
                            if not failed_vm_recheck:
                                self.__logger.warning(
                                    'junk machine {} has been deleted successfully'.format(
                                        machine_name
                                    )
                                )
                                break
                            else:
                                self.__logger.warning(
                                    'junk machine {} has not been deleted'.format(
                                        machine_name
                                    )
                                )
                    self.__sleep_between_tries()
                else:
                    self.__logger.debug('vms parent: {}'.format(vm.parent))
                    vm_uuid = vm.config.uuid
            except Exception:
                Settings.raven.captureException(exc_info=True)
                self.__logger.warning('pyvmomi related exception: ', exc_info=True)
                self.__sleep_between_tries()
            if vm:
                for retry in range(retry_deploy_count):
                    try:
                        self.vm_folders.move_vm_to_folder(vm_uuid, destination_folder_name)
                    except vim.fault.DuplicateName as e:
                        Settings.raven.captureException(exc_info=True)
                        self.__logger.warning(
                            'destination folder {} not created because {}; trying again'.format(
                                destination_folder_name,
                                e
                            )
                        )
                    except Exception as e:
                        Settings.raven.captureException(exc_info=True)
                        self.__logger.warning(
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
        container_view = None
        for rep in range(5):
            try:
                container_view = self.content.viewManager.CreateContainerView(
                                                                self.content.rootFolder,
                                                                [vim.VirtualMachine, vim.Folder],
                                                                True
                )

                for item in container_view.view:
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
                Settings.raven.captureException(exc_info=True)
                self.__sleep_between_tries()
            finally:
                self.__logger.debug('searching done')
                if container_view:
                    container_view.Destroy()
        return True

    def undeploy(self, machine_uuid):
        self.__check_connection()
        for attempt in range(6):
            try:
                vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
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
                    self.__logger.warning(
                        'machine {} not found or has been already deleted'.format(machine_uuid)
                    )
                    return
            except vmodl.fault.ManagedObjectNotFound:
                self.__logger.warning('problem while releasing machine {}'.format(machine_uuid))
                self.__sleep_between_tries()
            except Exception:
                Settings.raven.captureException(exc_info=True)
                self.__sleep_between_tries()

        raise RuntimeError("virtual machine hasn't been released")

    def freeze_vm(self, machine_uuid, timeout=15) -> bool:
        self.__logger.debug(f'-> freeze_vm(\'{machine_uuid}\')')
        self.__check_connection()
        vm = self.get_machine_by_uuid(machine_uuid)
        if not vm:
            raise RuntimeError(f'Could not find VM for uuid {machine_uuid}')

        is_frozen = vm.runtime.instantCloneFrozen
        is_running = vm.runtime.powerState == 'poweredOn'
        if not is_running:
            raise RuntimeError(f'Machine {repr(vm.name)} must be running to perform instant clone freeze')
        if is_frozen is True:
            raise RuntimeError(f'Cannot freeze machine \'{vm.name}\', because it is already frozen!')

        login_username = Settings.app.get('vms', {}).get('login_username', None)
        login_password = Settings.app.get('vms', {}).get('login_password', None)

        if not all([login_username, login_password]):
            raise RuntimeError('Cannot freeze machine, username or password not provided!')

        program_path = r'c:\Program Files\VMware\VMware Tools\vmtoolsd.exe'
        program_args = '--cmd "instantclone.freeze"'
        self.run_process_in_vm(machine_uuid=machine_uuid,
                               username=login_username,
                               password=login_password,
                               program_path=program_path,
                               program_arguments=program_args,
                               run_async=True)
        for i in range(timeout):
            is_frozen = vm.runtime.instantCloneFrozen
            self.__logger.debug(f'instantCloneFrozen: {is_frozen}')
            if is_frozen is True:
                break
            self.__logger.debug('<> sleep(1)')
            time.sleep(1)

        self.__logger.debug(f'<- freeze(): {is_frozen}')
        return is_frozen

    def start(self, machine_uuid):
        self.__check_connection()

        vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
        if vm:
            self.__logger.debug('found vm: {}'.format(vm.config.uuid))
            task = vm.PowerOnVM_Task()
            self.wait_for_task(task)
            self.__logger.debug('vm powered on')
        else:
            raise Exception('machine {} not found'.format(machine_uuid))

    def stop(self, machine_uuid):
        self.__check_connection()
        for i in range(Settings.app['vsphere']['retries']['config_network']):
            try:
                vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
                if vm:
                    self.__logger.debug('found vm: {}'.format(machine_uuid))
                    task = vm.PowerOffVM_Task()
                    self.wait_for_task(task)
                    self.__logger.debug('vm powered off')
                    return
                else:
                    raise Exception('machine {} not found'.format(machine_uuid))
            except Exception:
                Settings.raven.captureException(exc_info=True)
                self.__sleep_between_tries()

    def reset(self, machine_uuid):
        self.__check_connection()
        vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
        if not vm:
            raise Exception('machine {} not found'.format(machine_uuid))
        self.__logger.debug('found vm: {}'.format(vm.config.uuid))
        # invoke reset - it does not fail even in case VM is powered off!
        task = vm.ResetVM_Task()
        self.wait_for_task(task)
        self.__logger.debug('vm reset done')

    def _take_screenshot_to_datastore(self, machine_uuid):
        """
        Takes screenshot of VM and saves it in datastore
        :param machine_uuid: machine uuid
        :return: tuple; name of datastore (where screenshot is saved)
        and path to screenshot in datastore
        """
        self.__logger.debug('-> take_screenshot()')
        self.__check_connection()
        vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
        if vm is None:
            raise Exception(f'machine {machine_uuid} not found')

        self.__logger.debug(f'found vm: {vm.config.uuid}')
        screenshot_task = vm.CreateScreenshot_Task()
        self.wait_for_task(screenshot_task)
        result_path = screenshot_task.info.result
        if not result_path:
            return None, None
        # can't we just use self.destination_datastore.info.name ?
        datastore_name, screenshot_path = result_path.split(' ')
        datastore_name = datastore_name.lstrip('[').rstrip(']')
        self.__logger.debug(f'<- take_screenshot: {datastore_name}, {screenshot_path}')
        return datastore_name, screenshot_path

    @staticmethod
    def _store_screenshot_to_hcp(machine_uuid: str, screenshot_data) -> str:
        hcp_server = Settings.app['hcp']['url']
        hcp_auth = Settings.app['hcp']['auth']
        hcp_base_dir = Settings.app['hcp']['base_dir']

        hcp_filename = f'{machine_uuid}_{uuid.uuid4()}.png'
        upload_url = f'{hcp_server}/rest/{hcp_base_dir}/{hcp_filename}'
        put_request = urllib.request.Request(
            upload_url,
            method='PUT',
            data=screenshot_data,
        )
        put_request.add_header('Content-Length', str(len(screenshot_data)))
        put_request.add_header('Content-Type', 'multipart/form-data')
        put_request.add_header('Authorization', hcp_auth)
        ssl_context = ssl._create_unverified_context()
        response = urllib.request.urlopen(
            put_request,
            context=ssl_context,
            timeout=Settings.app['hcp'].get('timeout', 120)
        )
        if response.code != 201:
            Settings.raven.captureMessage(
                f'problem uploading data to hcp: {hcp_server}, {upload_url} -> {response.code}'
            )
        return upload_url.replace('/rest/', '/hs3/')

    def take_screenshot(self, machine_uuid: str, store_to: str = 'db') -> Union[bytes, str]:
        """
        Takes screenshot of VM and returns it as base64 encoded string or hcp url
        :param machine_uuid: machine uuid
        :param store_to: screenshot destination, db or hcp for now
        :return: base64 encoded string, or hcp url or None in case of failure
        """
        datastore, path = self._take_screenshot_to_datastore(machine_uuid=machine_uuid)
        self.__logger.debug(f'datastore: {datastore}, path: {path}')
        if datastore is not None or path is not None:
            screenshot_data = self.get_file_bytes_from_datastore(datastore_name=datastore, remote_path_to_file=path)
            if screenshot_data:
                if store_to == "hcp":
                    return self._store_screenshot_to_hcp(machine_uuid, screenshot_data)
                elif store_to == "db":
                    return base64.b64encode(screenshot_data)
                else:
                    Settings.raven.captureMessage(f'invalid store_to specification ({store_to})')
            else:
                Settings.raven.captureMessage('Error obtaining screenshot data')

    def take_snapshot(self, machine_uuid, snapshot_name) -> bool:
        self.__logger.debug(f'-> take_snapshot({machine_uuid}, {snapshot_name})')
        vm = self.get_machine_by_uuid(machine_uuid=machine_uuid)
        snapshot_task = vm.CreateSnapshot_Task(
            name=snapshot_name,
            description='',
            memory=True,
            quiesce=False
        )
        self.wait_for_task(snapshot_task)
        result = snapshot_task.info.state == 'success' and snapshot_task.info.error is None
        self.__logger.debug(f'<- take_snapshot(): {result}')
        return result

    def remove_snapshot(self, machine_uuid, snapshot_name):
        self.__logger.debug(f'-> remove_snapshot({machine_uuid}, {snapshot_name})')
        vm = self.get_machine_by_uuid(machine_uuid)
        snap = self.search_for_snapshot(vm=vm, snapshot_name=snapshot_name)
        remove_task = snap.RemoveSnapshot_Task(removeChildren=False)
        self.wait_for_task(remove_task)
        self.__logger.debug(f'<- remove_snapshot()')

    def revert_snapshot(self, machine_uuid, snapshot_name):
        self.__logger.debug(f'-> revert_snapshot({machine_uuid}, {snapshot_name})')
        vm = self.get_machine_by_uuid(machine_uuid)
        snap = self.search_for_snapshot(vm=vm, snapshot_name=snapshot_name)
        revert_task = snap.RevertToSnapshot_Task()
        self.wait_for_task(revert_task)
        # revert task does not give any result explicitly! So we check for 'success' and no error
        result = revert_task.info.state == 'success' and revert_task.info.error is None
        self.__logger.debug(f'<- revert_snapshot(): {result}')
        return result

    # TODO rewrite others to use this one
    def __get_objects_list_from_container(self, container, object_type):

        result = []
        object_view = None
        try:
            object_view = self.content.viewManager.CreateContainerView(
                    container,
                    [object_type],
                    True)
            result = list(object_view.view)
        except vmodl.fault.ManagedObjectNotFound:
            self.__logger.warning('vmodl.fault.ManagedObjectNotFound has occurred')
        except Exception:
            Settings.raven.captureException(exc_info=True)
        finally:
            if object_view is not None:
                object_view.Destroy()

        return result

    def __get_datacenter_for_datastore(self, datastore_name):
        dcs = self.__get_objects_list_from_container(self.content.rootFolder, vim.Datacenter)
        for dc in dcs:
            data_stores = self.__get_objects_list_from_container(dc, vim.Datastore)
            for ds in data_stores:
                if ds.info.name == datastore_name:
                    return dc
        return None

    def get_file_bytes_from_datastore(self, remote_path_to_file, datastore_name):
        """
        Downloads file from datastore (with retries) and returns its data.
        Note: keep in mind requested file size, since data are in memory!
        :param remote_path_to_file: path to file in datastore (e.g. my_vm/my_vm.png)
        :param datastore_name: name of datastore
        :return: data
        """
        self.__check_connection()
        server_name = Settings.app['vsphere']['host']
        datacenter = self.__get_datacenter_for_datastore(datastore_name)
        if datacenter is None:
            raise RuntimeError(f'Cannot find datacenter for datastore {datastore_name}')

        url = f'https://{server_name}/folder/{remote_path_to_file}?dcPath={datacenter.name}&dsName={datastore_name}'

        for i in range(3):
            try:
                # resp = requests.get(url=url, verify=False, headers={'Cookie': self._connection_cookie})
                # the cookie usage was dropped because the new solution improved stability
                resp = requests.get(
                    url=url,
                    verify=False,
                    auth=(Settings.app['vsphere']['username'], Settings.app['vsphere']['password'])
                )
                if resp.status_code == 200:
                    # download ok, save return path
                    return resp.content
                else:
                    # try again
                    msg = f'Download of {remote_path_to_file} (retry {i}) failed with status code: {resp.status_code}'
                    self.__logger.warning(msg)
                    self.__sleep_between_tries()
                    continue
            except Exception as e:
                self.__logger.warning(f'Downloading of {remote_path_to_file} (retry {i}) failed: {e}')
                Settings.raven.captureException(exc_info=True)

        # failed, nothing to return
        return None

    def config_network(self, device_uuid, **kwargs):
        self.__logger.debug('config_network')
        self.__check_connection()
        for i in range(Settings.app['vsphere']['retries']['config_network']):
            try:

                vm = self.content.searchIndex.FindByUuid(None, device_uuid, True)

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

    def _get_machine_nos_id(self, vm, machine_uuid):
        result = ''
        try:
            for hw in vm.config.hardware.device:
                try:
                    mac = hw.macAddress
                    if Settings.app['nosid_prefix'] is None:
                        result = "v{}".format(re.sub(':', '', str(mac).upper()))
                    else:
                        result = "{}{}".format(
                            Settings.app['nosid_prefix'],
                            re.sub(':', '', str(mac).upper())
                        )
                except AttributeError:
                    pass
        except Exception:
            self.__logger.debug("obtaining nos_id on machine {} failed".format(machine_uuid), exc_info=True)
        finally:
            return result

    def run_process_in_vm(self, machine_uuid, username, password, program_path, program_arguments='', run_async=False) -> Optional[int]:
        """
        Runs process with args in VM under 'username', using VMWare tools
        :param machine_uuid: VM UUID specification
        :param username: login username of user in VM
        :param password: login password for 'username' in VM
        :param program_path: path to program
        :param program_arguments: optional, program arguments
        :param run_async: do not wait for process end
        :return: exit code of process (if not running async)

        Note: Process stderr and stdout is not collected as it's not directly supported by VMWare tools

        """
        self.__logger.debug(f'-> run_process_in_vm({machine_uuid}, {username}, ***, {program_path}, {program_arguments}, {run_async})')
        sleep_delta = 0.5
        vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
        creds = vim.vm.guest.NamePasswordAuthentication(username=username, password=password)
        program_spec = vim.vm.guest.ProcessManager.ProgramSpec(programPath=program_path, arguments=program_arguments)
        process_manager = self.content.guestOperationsManager.processManager
        res = process_manager.StartProgramInGuest(vm, creds, program_spec)
        if res > 0:
            result = None
            while run_async is False:
                process_info = process_manager.ListProcessesInGuest(vm, creds, [res]).pop()
                pid_exitcode = process_info.exitCode
                if isinstance(pid_exitcode, int):
                    self.__logger.debug(f'Process pid {process_info.pid} {process_info.cmdLine} finished;\n{process_info}')
                    result = pid_exitcode
                    break
                else:
                    self.__logger.debug(f'Process pid {process_info.pid} {process_info.cmdLine} still running; sleep({sleep_delta})')
                    time.sleep(sleep_delta)
            self.__logger.debug(f'<- run_process_in_vm(): {repr(result)}')
            return result
        else:
            raise RuntimeError(f"Could not start {program_spec.programPath} process!")

    def _get_machine_ips(self, vm, machine_uuid):
        result = []
        try:
            for adapter in vm.guest.net:
                for ip in adapter.ipConfig.ipAddress:
                    result.append(ip.ipAddress)
        except Exception:
            self.__logger.debug("obtaining ips on machine {} failed".format(machine_uuid), exc_info=True)
        finally:
            return result

    def _get_machine_name(self, vm, machine_uuid):
        result = "unknown"
        for i in range(Settings.app['vsphere']['retries']['default']):
            try:
                result = vm.config.name
            except Exception:
                self.__logger.debug("obtaining machine name {} failed".format(machine_uuid), exc_info=True)
        return result

    def get_machine_info(self, machine_uuid):
        self.__check_connection()
        result = {'ip_addresses': [], 'nos_id': '', 'machine_search_link': ''}

        vm = self.content.searchIndex.FindByUuid(None, machine_uuid, True)
        try:
            if vm:
                self.__logger.debug('found vm: {}'.format(machine_uuid))
                result['ip_addresses'] = self._get_machine_ips(vm, machine_uuid)
                result['nos_id'] = self._get_machine_nos_id(vm, machine_uuid)

                machine_name = self._get_machine_name(vm, machine_uuid)
                result['machine_name'] = machine_name

                host_name = Settings.app['vsphere']['host']
                vsphere_address = 'https://{}/'.format(host_name)

                result['machine_search_link'] = '{}{}{}{}'.format(
                    vsphere_address,
                    'ui/#?extensionId=vsphere.core.search.domainView&query=',
                    machine_name,
                    '&searchType=simple'
                    )

                self.__logger.debug('get machine info end')
        except Exception:
            self.__logger.debug('get machine info on {} failed'.format(machine_uuid), exc_info=True)
        finally:
            return result

    def wait_for_task(self, task):
        # this function is as ugly as possible but written in this way for stability purposes.
        # the number of callings to pyvmomi library is restricted as much as possible.
        while True:
            state = task.info.state
            if state == 'success' or state == 'error':
                break
            message = "no-message"
            progress = "n/a"
            try:
                progress = task.info.progress
                message = task.info.description.message
            except Exception:
                self.__logger.warning('Problem obtaining progress or description on a vsphere task')

            self.__logger.debug('Progress {}% | Task: {}\r'.format(
                progress,
                message
            ))
            time.sleep(0.5)

        result = task.info.result
        error_msg = f', message: {task.info.error.msg}' if state == 'error' else ''
        self.__logger.debug(f'Task finished with status: {state}{error_msg}, result: {result}')

        return result

    class VmFolders:

        def __init__(self, parent):
            # this stores all folders in vsphere at the time the class was instantiated
            self.vm_folders = {}
            # this stores all sub folders where this lm unit operates
            self.system_folders = {}

            self.__logger = logging.getLogger(__name__)
            self.parent = parent
            self.__collect_all_folders()

        @staticmethod
        def __sleep_between_tries():
            time.sleep(random.uniform(
                            Settings.app['vsphere']['retries']['delay_period_min'],
                            Settings.app['vsphere']['retries']['delay_period_max']
            )
            )

        def __get_system_root_folder(self):
            if not Settings.app['vsphere']['folder'] in self.vm_folders:
                self.__logger.warning('{} not in vm_folders'.format(Settings.app['vsphere']['folder']))
                # self.__logger.warn('{}'.format(self.vm_folders.keys()))
            folder = self.vm_folders[Settings.app['vsphere']['folder']]
            # self.__logger.debug('folder: {}'.format(folder))

            container_view = self.parent.content.viewManager.CreateContainerView(
                self.parent.content.rootFolder,
                [vim.Folder],
                True
            )

            try:
                for item in container_view.view:
                    if str(item) == folder:
                        return item
                raise Exception("root folder not obtained")
            finally:
                container_view.DestroyView()

        def create_subfolder(self, path, subpath):
            self.__logger.debug("A request to create {} in {}".format(subpath, path))
            container_view = self.parent.content.viewManager.CreateContainerView(
                # we have to start from parent to find the current root folder
                self.__get_system_root_folder().parent,
                [vim.Folder],
                True
            )

            new_folder = None
            for item in container_view.view:
                if str(item) == self.system_folders[path]:
                    self.__logger.debug('parent folder {} found'.format(path))
                    try:
                        new_folder = item.CreateFolder(name=subpath)
                        break
                    except vim.fault.DuplicateName:
                        self.__sleep_between_tries()
                        break

            container_view.DestroyView()
            self.__logger.debug("creation done.")
            self.__collect_system_folders()
            return new_folder

        def __obtain_folder(self, path):
            container_view = self.parent.content.viewManager.CreateContainerView(
                self.__get_system_root_folder().parent,
                [vim.Folder],
                True
            )
            try:
                for item in container_view.view:
                    if path in self.system_folders and str(item) == self.system_folders[path]:
                        return item
            finally:
                container_view.DestroyView()

            self.__logger.warning("folder: {} not found".format(path))

        def create_folder(self, folder_path):
            self.__collect_system_folders()
            path = self.__correct_folder_format(folder_path)
            if path in self.system_folders:
                return self.__obtain_folder(path)

            items = path.split('/')
            for split_index in range(2, len(items)):
                temp_path = '/'.join(items[:split_index])
                next_folder = items[split_index:][0]
                if temp_path+'/'+next_folder not in self.system_folders:
                    self.create_subfolder(temp_path, next_folder)
                else:
                    self.__logger.debug('{} exists'.format(temp_path+'/'+next_folder))

            if path not in self.system_folders:
                self.__logger.warning("Directory {} not created".format(path))
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
            container_view = None
            for repetition in range(5):
                try:
                    root_folder_moref = self.__get_system_root_folder()
                    container_view = self.parent.content.viewManager.CreateContainerView(
                        root_folder_moref,
                        [vim.Folder],
                        True
                    )

                    self.__logger.debug("collecting system vm folders....")
                    self.__logger.debug("\troot_folder_moref: {}".format(str(root_folder_moref)))
                    self.system_folders = {
                        Settings.app['vsphere']['folder']: str(root_folder_moref)
                    }
                    # all parent folders must be initially added as well
                    for i in self.vm_folders.keys():
                        if Settings.app['vsphere']['folder'].startswith(i):
                            self.system_folders[i] = self.vm_folders[i]

                    for item in container_view.view:
                        full_name = self.__retrieve_full_folder_path(item)
                        self.system_folders[full_name] = str(item)

                    return
                except vmodl.fault.ManagedObjectNotFound as monf:
                    self.__logger.warning(
                        "collect_system_folders failed attempt: {}, due to {}".format(repetition, monf)
                    )
                    self.__sleep_between_tries()
                except Exception as e:
                    Settings.raven.captureException(exc_info=True)
                    self.__logger.error(
                        "collect_system_folders failed attempt: {}, due to {}".format(repetition, e)
                    )
                    raise e
                finally:
                    if container_view:
                        container_view.DestroyView()

        def __collect_all_folders(self):
            container_view = None
            for repetition in range(5):
                try:
                    container_view = self.parent.content.viewManager.CreateContainerView(
                        self.parent.content.rootFolder,
                        [vim.Folder],
                        True
                    )

                    self.__logger.debug("collecting all vm folders....")
                    self.vm_folders = {}
                    for item in container_view.view:
                        full_name = self.__retrieve_full_folder_path(item)
                        self.vm_folders[full_name] = str(item)
                    self.__logger.debug("collecting done.")
                    return
                except vmodl.fault.ManagedObjectNotFound as monf:
                    self.__logger.warning("collect_all_folders failed attempt: {}, due to {}".format(repetition, monf))
                    self.__sleep_between_tries()
                except Exception as e:
                    Settings.raven.captureException(exc_info=True)
                    self.__logger.error("collect_all_folders failed attempt: {}, due to {}".format(repetition, e))
                    raise e
                finally:
                    if container_view:
                        container_view.DestroyView()

        def __move_vm_to_existing_folder(self, vm, existing_path):
            container_view = self.parent.content.viewManager.CreateContainerView(
                self.__get_system_root_folder(),
                [vim.Folder],
                True
            )
            for item in container_view.view:
                if str(item) == self.system_folders[existing_path]:
                    task = item.MoveIntoFolder_Task(list=[vm])
                    while task.info.state == 'running' or task.info.state == 'queued':
                        time.sleep(0.2)
            container_view.DestroyView()

        def __retrieve_full_folder_path(self, folder):
            if isinstance(folder.parent, vim.Folder):
                return "{}/{}".format(
                    self.__retrieve_full_folder_path(folder.parent),
                    folder.name
                )
            else:
                return "/{}".format(folder.name)

        @staticmethod
        def __correct_folder_format(folder):
            f_folder = re.sub(r'[/\s]*$', '', folder)
            if not f_folder.startswith('/vm/'):
                msg = f'correct folder definition must look like "/vm/root_folder/subfolder/..." not {f_folder}'
                raise Exception(msg)

            return f_folder
