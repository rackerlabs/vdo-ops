from pyVim import connect
from pyVmomi import vim
import requests
from common import log


logger = log.setup_logging()


class VmNotFound(Exception):
    pass


class InvalidLoginVCenter(Exception):
    pass


class VCenterConnectionError(Exception):
    pass


class VirtualMachineConnectionParameters:
    def __init__(self, uuid, username, password):
        self.uuid = uuid
        self.username = username
        self.password = password


class VcenterConnectionParameters:
    def __init__(self, host, username, password, port=443):
        self.host = host
        self.username = username
        self.password = password
        self.port = port


class VsphereClient:
    def __init__(self, vc_params: VcenterConnectionParameters):
        self.vc_params = vc_params


class AlarmsClient(VsphereClient):
    def list_alarms(self):
        """
        Lists the names of all alarms defined at the root of the vCenter.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            root_folder = content.rootFolder

            alarm_states = root_folder.declaredAlarmState

            return [alarm_state.alarm.info.name for alarm_state in alarm_states]

    def remove_alarm(self, name):
        """
        Removes the alarm with the given name, if it exists.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            root_folder = content.rootFolder

            alarm_states = root_folder.declaredAlarmState

            alarm = next(
                (
                    alarm_state.alarm
                    for alarm_state in alarm_states
                    if alarm_state.alarm.info.name == name
                ),
                None,
            )

            if not alarm:
                raise Exception(
                    f"no alarm with name {name} was found at the root of the vCenter"
                )

            alarm.RemoveAlarm()

    def alarm_exists(self, name):
        """
        Returns whether an alarm with the given name if it exists on the root folder
        of the vCenter inventory tree.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            root_folder = content.rootFolder

            alarm_states = root_folder.declaredAlarmState

            return (
                next(
                    (
                        alarm_state.alarm
                        for alarm_state in alarm_states
                        if alarm_state.alarm.info.name == name
                    ),
                    None,
                )
                is not None
            )

    def create_alarm(self, spec):
        """
        Creates a new alarm on the root folder of the vCenter inventory tree.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            root_folder = content.rootFolder
            alarm_manager = content.alarmManager
            return alarm_manager.CreateAlarm(root_folder, spec)

    def debug_print_alarm(self, name):
        """
        Prints the contents of an alarm with the given name for development
        or debug purposes.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            root_folder = content.rootFolder

            alarm_states = root_folder.declaredAlarmState

            alarm = next(
                (
                    alarm_state.alarm
                    for alarm_state in alarm_states
                    if alarm_state.alarm.info.name == name
                ),
                None,
            )

            if alarm:
                print(alarm.info)
            else:
                print("alarm not found")


class GuestOperationsApiClient(VsphereClient):
    def __init__(
        self,
        vc_params: VcenterConnectionParameters,
        vm_params: VirtualMachineConnectionParameters,
    ):
        super().__init__(vc_params)
        self.vm_params = vm_params

    def execute_command(self, command, arguments):
        """
        Executes a command from within the VM's guest OS and returns the process ID.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()

            # https://www.vmware.com/support/orchestrator/doc/vco_vsphere55_api/html/VcSearchIndex.html
            datacenter = None
            vm_search = True
            instance_uuid = True

            vm = content.searchIndex.FindByUuid(
                datacenter, self.vm_params.uuid, vm_search, instance_uuid
            )
            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.vm_params.username, password=self.vm_params.password
            )
            program_spec = vim.vm.guest.ProcessManager.ProgramSpec(
                programPath=command, arguments=arguments
            )

            return content.guestOperationsManager.processManager.StartProgramInGuest(
                vm, creds, program_spec
            )

    def get_exit_code(self, process_id):
        """
        Returns the exit code of the process identified by the given process ID
        if it has completed execution. If the process is still executing, None
        is returned.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()

            vm = content.searchIndex.FindByUuid(None, self.vm_params.uuid, True, True)
            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.vm_params.username, password=self.vm_params.password
            )

            processes = content.guestOperationsManager.processManager.ListProcessesInGuest(
                vm, creds, [process_id]
            )
            if processes:
                return processes.pop().exitCode
            else:
                raise Exception("Guest Ops Process not found")

    def delete_file(self, file_path):
        """
        Deletes a file from within a VM.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            vm = content.searchIndex.FindByUuid(None, self.vm_params.uuid, True)
            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.vm_params.username, password=self.vm_params.password
            )

            content.guestOperationsManager.fileManager.DeleteFileInGuest(
                vm, creds, file_path
            )

    def copy_file_from_vm(self, file_path):
        """
        Downloads a file from a VM.

        The method returns a requests response object with a streamed response entity.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            vm = content.searchIndex.FindByUuid(None, self.vm_params.uuid, True)
            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.vm_params.username, password=self.vm_params.password
            )

            download_url = content.guestOperationsManager.fileManager.InitiateFileTransferFromGuest(
                vm, creds, file_path
            )

            upload_response = requests.get(  # nosec
                download_url, verify=False, stream=True
            )
            upload_response.raise_for_status()

    def copy_file_to_vm(self, file_stream, file_size, file_path):
        """
        Uploads a file to a VM.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()
            vm = content.searchIndex.FindByUuid(None, self.vm_params.uuid, True)
            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.vm_params.username, password=self.vm_params.password
            )

            file_attribute = vim.vm.guest.FileManager.FileAttributes()
            upload_url = content.guestOperationsManager.fileManager.InitiateFileTransferToGuest(
                vm, creds, file_path, file_attribute, file_size, True
            )

            upload_response = requests.put(  # nosec
                upload_url, data=file_stream, verify=False
            )
            upload_response.raise_for_status()

    def validate_credentials(self):
        """
        Validates the credentials of a given VM
        """
        with vcenter_connection(self.vc_params) as service_instance:
            content = service_instance.RetrieveContent()

            vm = content.searchIndex.FindByUuid(None, self.vm_params.uuid, True, True)

            if not vm:
                raise VmNotFound(
                    f"no VM with UUID {self.vm_params.uuid} was found in the vCenter"
                )

            creds = vim.vm.guest.NamePasswordAuthentication(
                username=self.vm_params.username, password=self.vm_params.password
            )

            return content.guestOperationsManager.authManager.ValidateCredentialsInGuest(
                vm, creds
            )


class VirtualMachineClient(VsphereClient):
    def is_vm_powered_on(self, vm_uuid):
        """
        Given a VM UUID, checks to see if it is powered on.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            # FindByUuid takes:
            # datacenter - when set to None, searches the entire vCenter
            # vm_uuid - UUID of the VM (in this case the instance UUID)
            # vm_search - set to True to indicate that we are looking for a VM
            # instance_uuid - set to True to indicate we are using an instance UUID (as opposed to BIOS)
            vm = service_instance.RetrieveContent().searchIndex.FindByUuid(
                None, vm_uuid, True, True
            )

            if not vm:
                raise VmNotFound(f"no VM with UUID {vm_uuid} was found in the vCenter")

            return vm.runtime.powerState == "poweredOn"

    def guest_tools_running_on_vm(self, vm_uuid):
        """
        Given a VM UUID, checks to see if it is powered on.
        """
        with vcenter_connection(self.vc_params) as service_instance:
            # FindByUuid takes:
            # datacenter - when set to None, searches the entire vCenter
            # vm_uuid - UUID of the VM (in this case the instance UUID)
            # vm_search - set to True to indicate that we are looking for a VM
            # instance_uuid - set to True to indicate we are using an instance UUID (as opposed to BIOS)
            vm = service_instance.RetrieveContent().searchIndex.FindByUuid(
                None, vm_uuid, True, True
            )

            if not vm:
                raise VmNotFound(f"no VM with UUID {vm_uuid} was found in the vCenter")

            return vm.guest.toolsRunningStatus == "guestToolsRunning"

    def get_content(self):
        """
        Retrieve all content
        """
        with vcenter_connection(self.vc_params) as service_instance:
            return service_instance.RetrieveContent()


class vcenter_connection:
    def __init__(self, vc_params: VcenterConnectionParameters):
        self.vc_params = vc_params

    def __enter__(self):
        try:
            self.service_instance = connect.SmartConnectNoSSL(
                host=self.vc_params.host,
                user=self.vc_params.username,
                pwd=self.vc_params.password,
                port=self.vc_params.port,
            )
        except vim.fault.InvalidLogin:
            raise InvalidLoginVCenter("VCenter login credentials were invalid.")
        except Exception:
            raise VCenterConnectionError("Unable to connect to the VCenter.")
        return self.service_instance

    def __exit__(self, exc_type, exc_val, exc_tb):
        connect.Disconnect(self.service_instance)
