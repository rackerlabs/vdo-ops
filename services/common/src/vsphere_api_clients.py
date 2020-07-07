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


class NetworkCopyClient(VsphereClient):
    def getPortgroupsByVirtualSwitch(self, vswitch_name):
        return None

    def isInDoNotCopyList(self, portgroup_name):
        return None

    def hasVirtualSwitch(self, vswitch_name):
        return None

    def hasPortgroup(self, portgroup_name):
        return None

    def addVirtualSwitch(self, vswitch):
        return None

    def addPortgroup(self, portgroup):
        return None


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
