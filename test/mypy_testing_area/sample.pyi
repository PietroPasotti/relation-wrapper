from enum import Enum
from typing import Any, Generic, Literal, TypeVar, overload

_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")
_D = TypeVar("_D")

_U = TypeVar("_U")

_DMReq = TypeVar("_DMReq", bound="DataBagModel")
_DMProv = TypeVar("_DMProv", bound="DataBagModel")
_DM = TypeVar("_DM", bound="DataBagModel")

class DataBagModel(Generic[_A, _U]):
    app: _A
    unit: _U
    def __init__(self, app: _A, unit: _U) -> None: ...

class Role(Enum):
    requirer: int
    provider: int

class Template(Generic[_DMReq, _DMProv]):
    requirer: _DMReq
    provider: _DMProv
    def __init__(self, requirer: _DMReq, provider: _DMProv) -> None: ...

class Relation(Generic[_A, _B, _C, _D]):
    app: _A
    unit: _B
    def __init__(
        self, template: Template[_DMReq, _DMProv], role: Literal["requirer", "provider"]
    ) -> None: ...

@overload
def wrap_relation(
    template: Template[DataBagModel[_A, _B], DataBagModel[_C, _D]],
    role: Literal["requirer"],
) -> Relation[_A, _B, _C, _D]: ...
@overload
def wrap_relation(
    template: Template[DataBagModel[_A, _B], DataBagModel[_C, _D]],
    role: Literal["provider"],
) -> Relation[_C, _D, _A, _B]: ...
def make_template(
    requirer: DataBagModel[_A, _B], provider: DataBagModel[_C, _D]
) -> Template[DataBagModel[_A, _B], DataBagModel[_C, _D]]: ...
