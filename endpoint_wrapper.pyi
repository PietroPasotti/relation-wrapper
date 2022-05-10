import collections
from enum import Enum
from typing import Any, Generic, Literal, TypeVar, overload, Type, Callable, \
    Protocol, Mapping, Optional, Union, Iterable, Tuple, Dict, List

from ops.charm import CharmBase
from ops.framework import Object
from ops.model import Relation as OpsRelation, Application, Unit

# fixme avoid duplication of Role and _Validator
Role = Literal["requirer", "provider"]

_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")
_D = TypeVar("_D")

_U = TypeVar("_U")

_DMReq = TypeVar("_DMReq", bound="DataBagModel")
_DMProv = TypeVar("_DMProv", bound="DataBagModel")
_DM = TypeVar("_DM", bound="DataBagModel")

class DataBagModel:
    app: Optional[Type[Any]]
    unit: Optional[Type[Any]]
    def to_dict(self) -> dict: ...
    def __init__(self, app, unit) -> None: ...

class Template:
    requirer: Optional[DataBagModel]
    provider: Optional[DataBagModel]
    def as_requirer_model(self) -> RelationModel: ...
    def as_provider_model(self) -> RelationModel: ...
    def to_dict(self) -> dict: ...
    def __init__(self, requirer, provider) -> None: ...

class RelationModel(Generic[_A, _B, _C, _D]):
    local_app_data_model: _A
    remote_app_data_model: _B
    local_unit_data_model: _C
    remote_unit_data_model: _D
    @staticmethod
    def from_charm(charm: CharmBase, relation_name: str, template: Template = ...) -> RelationModel: ...
    def get(self, name): ...
    def __init__(self, local_app_data_model, remote_app_data_model, local_unit_data_model, remote_unit_data_model) -> None: ...

_RelationModel = TypeVar("_RelationModel", bound=RelationModel)

class ValidationError(RuntimeError): ...
class CoercionError(ValidationError): ...
class InvalidFieldNameError(ValidationError): ...
class CannotWriteError(RuntimeError): ...

class _Validator(Protocol):
    _parse_obj_as: Callable[[Type, Any], str]
    _parse_raw_as: Callable[[Type, str], Any]
    _model: Any
    model: Any
    def validate(self, data: dict, _raise: bool = ...): ...
    def check_field(self, name): ...
    def coerce(self, key, value): ...
    def serialize(self, key, value) -> str: ...
    def deserialize(self, obj: str, value: str) -> Any: ...

_ValidatorType = TypeVar('_ValidatorType', bound=_Validator)

class DataclassValidator(_Validator):
    model: Any

class PydanticValidator(_Validator):
    model: Any
    _BaseModel: Type
    _PydanticValidationError: Type[BaseException]


DEFAULT_VALIDATOR: Union[Type[PydanticValidator], Type[DataclassValidator]]

UnitOrApplication = Union[Unit, Application]
T = TypeVar("T")

class DataWrapper(Generic[T]):
    can_write: bool
    valid: Optional[bool]
    data: T
    def __init__(self, relation: OpsRelation, entity: UnitOrApplication, model: Any, validator: _Validator, can_write: bool = ...) -> None: ...
    def validate(self) -> None: ...

ModelName = Literal["local_app", "remote_app", "local_unit", "remote_unit"]

class Relation(Generic[_A, _B, _C, _D]):
    _relation: OpsRelation
    _remote_units: Tuple[Unit]
    _remote_app: Application
    _relation_model: Optional[RelationModel]
    _validator: Optional[Type[_ValidatorType]]
    _is_leader: bool
    _local_app: Application
    _local_unit: Unit

    def __init__(self, charm: CharmBase, relation: OpsRelation, model: RelationModel, validator: Type['_Validator'] = ...) -> None: ...
    def _wrap_data(self, entity: UnitOrApplication, model_name: ModelName, can_write=False) -> DataWrapper: ...
    def wraps(self, relation: OpsRelation) -> bool: ...
    @property
    def relation(self) -> OpsRelation: ...
    @property
    def remote_units(self) -> Tuple[Unit]: ...
    @property
    def remote_app(self) -> Application: ...
    @property
    def remote_units_valid(self) -> Optional[bool]: ...
    @property
    def remote_app_valid(self) -> Optional[bool]: ...
    @property
    def local_unit_valid(self) -> Optional[bool]: ...
    @property
    def local_app_valid(self) -> Optional[bool]: ...
    @property
    def local_valid(self) -> Optional[bool]: ...
    @property
    def remote_valid(self) -> Optional[bool]: ...
    @property
    def valid(self) -> Optional[bool]: ...
    @property
    def local_app_data(self) -> DataWrapper[_A]: ...
    @property
    def remote_app_data(self) -> DataWrapper[_B]: ...
    @property
    def local_unit_data(self) -> DataWrapper[_C]: ...
    @property
    def remote_units_data(self) -> Mapping[Unit, DataWrapper[_D]]: ...

def get_worst_case(validity: Iterable[Optional[bool]]) -> Optional[bool]: ...

class _EndpointWrapper(Generic[_A, _B, _C, _D]):
    local_app: Application
    local_unit: Unit

    def __init__(self, charm: CharmBase, relation_name: str, template: Template = ..., role: Role = ..., validator: Type['_Validator'] = ..., **kwargs) -> None: ...
    def publish_defaults(self, event) -> None: ...
    def wrap(self, relation: OpsRelation) -> Relation: ...
    @property
    def relations(self) -> Tuple[Relation, ...]: ...
    @property
    def remote_units_valid(self): ...
    @property
    def remote_apps_valid(self): ...
    @property
    def local_unit_valid(self): ...
    @property
    def local_app_valid(self): ...
    @property
    def remote_valid(self): ...
    @property
    def local_valid(self): ...
    @property
    def valid(self): ...
    @property
    def local_app_data(self) -> Dict[Application, DataWrapper[_A]]: ...
    @property
    def remote_apps_data(self) -> Dict[Application, DataWrapper[_B]]: ...
    @property
    def local_unit_data(self) -> Dict[Application, DataWrapper[_C]]: ...
    @property
    def remote_units_data(self) -> Dict[Unit, DataWrapper[_D]]: ...



# template and requirer role
@overload
def EndpointWrapper(
    charm: CharmBase,
    relation_name: str,
    template: Template[DataBagModel[_A, _B], DataBagModel[_C, _D]],
    role: Literal["requirer"] = None,  # todo check this works
    validator: Optional[Type[_Validator]] = None,
    on_joined: Optional[Callable] = None,
    on_changed: Optional[Callable] = None,
    on_broken: Optional[Callable] = None,
    on_departed: Optional[Callable] = None,
    on_created: Optional[Callable] = None
) -> _EndpointWrapper[_A, _B, _C, _D]: ...
# template and provider role
@overload
def EndpointWrapper(
    charm: CharmBase,
    relation_name: str,
    template: Template[DataBagModel[_A, _B], DataBagModel[_C, _D]],
    role: Literal["provider"] = None,  # todo check this works
    validator: Optional[Type[_Validator]] = None,
    on_joined: Optional[Callable] = None,
    on_changed: Optional[Callable] = None,
    on_broken: Optional[Callable] = None,
    on_departed: Optional[Callable] = None,
    on_created: Optional[Callable] = None
) -> _EndpointWrapper[_C, _D, _A, _B]: ...
# no template, no role
@overload
def EndpointWrapper(
    charm: CharmBase,
    relation_name: str,
    template: Template = None,
    role: Role = None,
    validator: Optional[Type[_Validator]] = None,
    on_joined: Optional[Callable] = None,
    on_changed: Optional[Callable] = None,
    on_broken: Optional[Callable] = None,
    on_departed: Optional[Callable] = None,
    on_created: Optional[Callable] = None
) -> _EndpointWrapper: ...

def make_template(
    requirer: Optional[DataBagModel[_A, _B]] = None,
    provider: Optional[DataBagModel[_C, _D]] = None,
) -> Template[DataBagModel[_A, _B], DataBagModel[_C, _D]]: ...
@overload
def make_template(
    requirer_unit_model: Optional[_A] = None,
    requirer_app_model: Optional[_B] = None,
    provider_unit_model: Optional[_C] = None,
    provider_app_model: Optional[_D] = None,
) -> Template[DataBagModel[_A, _B], DataBagModel[_C, _D]]: ...
@overload
def make_template(
    requirer: Optional[DataBagModel[_A, _B]] = None,
    provider_unit_model: Optional[_C] = None,
    provider_app_model: Optional[_D] = None,
) -> Template[DataBagModel[_A, _B], DataBagModel[_C, _D]]: ...
@overload
def make_template(
    requirer_unit_model: Optional[_A] = None,
    requirer_app_model: Optional[_B] = None,
    provider: Optional[DataBagModel[_C, _D]] = None,
) -> Template[DataBagModel[_A, _B], DataBagModel[_C, _D]]: ...
