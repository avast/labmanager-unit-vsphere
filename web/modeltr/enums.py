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

    def has_finished(self):
        return self is RequestState.SUCCESS or self.is_error()

    def is_error(self):
        return self in [RequestState.FAILED, RequestState.TIMEOUTED, RequestState.ABORTED]