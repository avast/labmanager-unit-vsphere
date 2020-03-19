import enum


class UnitEnumBase(enum.Enum):

    def __str__(self):
        return self.value
