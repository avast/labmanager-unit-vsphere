import enum


class EnumBase(enum.Enum):
    def __str__(self):
        return self.value


class StrEnumBase(EnumBase):
    pass


class MachineState(StrEnumBase):

    CREATED = 'created'
    DEPLOYED = 'deployed'
    RUNNING = 'running'
    STOPPED = 'stopped'
    UNDEPLOYED = 'undeployed'
    FAILED = 'failed'
    ERRORED = 'errored'

    def can_be_changed(self) -> bool:
        """
        Machine state cannot be changed for failed and undeployed machines
        :return: bool
        """
        return self not in [MachineState.UNDEPLOYED, MachineState.FAILED]


class RequestState(StrEnumBase):
    CREATED = 'created'
    SUCCESS = 'success'
    FAILED = 'failed'
    DELAYED = 'delayed'
    TIMEOUTED = 'timeouted'
    ABORTED = 'aborted'

    def has_finished(self) -> bool:
        return self is RequestState.SUCCESS or self.is_error()

    def is_error(self) -> bool:
        return self in [RequestState.FAILED, RequestState.TIMEOUTED, RequestState.ABORTED]


class RequestType(StrEnumBase):
    DEPLOY = 'deploy'
    UNDEPLOY = 'undeploy'
    START = 'start'
    STOP = 'stop'
    RESET = 'reset'
    GET_INFO = 'get_info'
    TAKE_SCREENSHOT = 'take_screenshot'
    TAKE_SNAPSHOT = 'take_snapshot'
    RESTORE_SNAPSHOT = 'restore_snapshot'
    DELETE_SNAPSHOT = 'delete_snapshot'

    def can_change_machine_state(self) -> bool:
        return self in [RequestType.START, RequestType.STOP, RequestType.DEPLOY, RequestType.UNDEPLOY]
