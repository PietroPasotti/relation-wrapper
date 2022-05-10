from typing import Any, Generic, Literal, TypeVar, overload, Type, Callable, \
    Protocol, Mapping, Optional, Union, Iterable, Tuple, Dict, List

from ops.charm import CharmBase
from ops.model import Relation as OpsRelation, Application, Unit

Role = Literal["requirer", "provider"]

_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")
_D = TypeVar("_D")

_DMReq = TypeVar("_DMReq", bound=_DataBagModel)
_DMProv = TypeVar("_DMProv", bound=_DataBagModel)

class _DataBagModel(Generic[_A, _B]):
    app: Optional[_A]
    unit: Optional[_B]
    def to_dict(self) -> dict: ...
    def __init__(self, app, unit) -> None: ...

@overload
def DataBagModel(app:_A, unit:_B) -> _DataBagModel[_A, _B]:...
@overload
def DataBagModel(app:_A) -> _DataBagModel[_A, None]:...
@overload
def DataBagModel(unit:_B) -> _DataBagModel[None, _B]:...

class _Template(Generic[_DMProv, _DMReq]):
    provider: Optional[_DMProv]
    requirer: Optional[_DMReq]
    def as_requirer_model(self) -> RelationModel: ...  # unimportant to define _A, _B, _C, _D here...
    def as_provider_model(self) -> RelationModel: ...  # unimportant to define _A, _B, _C, _D here...
    def to_dict(self) -> dict: ...
    def __init__(self, requirer, provider) -> None: ...

class RelationModel(Generic[_A, _B, _C, _D]):
    local_app_data_model: _A
    remote_app_data_model: _B
    local_unit_data_model: _C
    remote_unit_data_model: _D
    @staticmethod
    def from_charm(charm: CharmBase, relation_name: str, template: _Template = ...) -> RelationModel: ...
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


class DataclassValidator(_Validator):
    _parse_obj_as: Callable[[Type, Any], str]
    _parse_raw_as: Callable[[Type, str], Any]
    _model: Any
    model: Any

class PydanticValidator(_Validator):
    _parse_obj_as: Callable[[Type, Any], str]
    _parse_raw_as: Callable[[Type, str], Any]
    _model: Any
    model: Any
    _BaseModel: Type
    _PydanticValidationError: Type[BaseException]


DEFAULT_VALIDATOR: Union[Type[PydanticValidator], Type[DataclassValidator]]

UnitOrApplication = Union[Unit, Application]
T = TypeVar("T")

class DataWrapperParams:
    relation: OpsRelation
    data: Any
    validator: _Validator
    validator: '_Validator'
    entity: 'UnitOrApplication'
    model: 'Model'
    can_write: bool


class DataWrapper(Generic[T]):
    __datawrapper_params__ : DataWrapperParams

    def __init__(self, relation: OpsRelation, entity: UnitOrApplication, model: Any, validator: _Validator, can_write: bool = ...) -> None: ...
    def validate(self) -> None: ...
    def __setitem__(self, key, value): ...
    def __getitem__(self, item): ...
    def __delitem__(self, key): ...
    def __iter__(self): ...
    def __len__(self): ...
    def __eq__(self, other) -> bool: ...
    def __bool__(self) -> bool: ...

ModelName = Literal["local_app", "remote_app", "local_unit", "remote_unit"]

class Relation(Generic[_A, _B, _C, _D]):
    _relation: OpsRelation
    _remote_units: Tuple[Unit]
    _remote_app: Application
    _relation_model: Optional[RelationModel]
    _validator: Optional[_Validator]
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
    def remote_units_data_valid(self) -> Optional[bool]: ...
    @property
    def remote_app_data_valid(self) -> Optional[bool]: ...
    @property
    def local_unit_data_valid(self) -> Optional[bool]: ...
    @property
    def local_app_data_valid(self) -> Optional[bool]: ...
    @property
    def local_valid(self) -> Optional[bool]: ...
    @property
    def remote_valid(self) -> Optional[bool]: ...
    @property
    def valid(self) -> Optional[bool]: ...
    @property
    def local_app_data(self) -> _A: ... # lie...
    @property
    def remote_app_data(self) -> _B: ... # lie...
    @property
    def local_unit_data(self) -> _C: ... # lie...
    @property
    def remote_units_data(self) -> Mapping[Unit, _D]: ... # lie...

def get_worst_case(validity: Iterable[Optional[bool]]) -> Optional[bool]: ...

class _EndpointWrapper(Generic[_A, _B, _C, _D]):
    local_app: Application
    local_unit: Unit

    def __init__(self, charm: CharmBase, relation_name: str, template: _Template = ..., role: Role = ..., validator: Type['_Validator'] = ..., **kwargs) -> None: ...
    def publish_defaults(self, event) -> None: ...
    def wrap(self, relation: OpsRelation) -> Relation[_A,_B,_C,_D]: ...
    @property
    def relations(self) -> Tuple[Relation[_A,_B,_C,_D], ...]: ...
    @property
    def remote_units_data_valid(self): ...
    @property
    def remote_apps_data_valid(self): ...
    @property
    def local_unit_data_valid(self): ...
    @property
    def local_app_data_valid(self): ...
    @property
    def remote_valid(self): ...
    @property
    def local_valid(self): ...
    @property
    def valid(self): ...
    @property
    def local_apps_data(self) -> Dict[Application, _A]: ... # we don't have Proxy[T] yet, so we can't correctly type DataWrapper. So we Hide it.
    @property
    def remote_apps_data(self) -> Dict[Application, _B]: ... # we don't have Proxy[T] yet, so we can't correctly type DataWrapper. So we Hide it.
    @property
    def local_units_data(self) -> Dict[Unit, _C]: ... # we don't have Proxy[T] yet, so we can't correctly type DataWrapper. So we Hide it.
    @property
    def remote_units_data(self) -> Dict[Unit, _D]: ... # we don't have Proxy[T] yet, so we can't correctly type DataWrapper. So we Hide it.


# template and requirer role
@overload
def EndpointWrapper(
    charm: CharmBase,
    relation_name: str,
    template: _Template[_DataBagModel[_A, _B], _DataBagModel[_C, _D]],
    role: Literal["requirer"] = None,
    validator: Optional[Type[_Validator]] = None,
    on_joined: Optional[Callable] = None,
    on_changed: Optional[Callable] = None,
    on_broken: Optional[Callable] = None,
    on_departed: Optional[Callable] = None,
    on_created: Optional[Callable] = None
) -> _EndpointWrapper[_C, _D, _A, _B]: ...
# template and provider role
@overload
def EndpointWrapper(
    charm: CharmBase,
    relation_name: str,
    template: _Template[_DataBagModel[_A, _B], _DataBagModel[_C, _D]],
    role: Literal["provider"] = None,
    validator: Optional[Type[_Validator]] = None,
    on_joined: Optional[Callable] = None,
    on_changed: Optional[Callable] = None,
    on_broken: Optional[Callable] = None,
    on_departed: Optional[Callable] = None,
    on_created: Optional[Callable] = None
) -> _EndpointWrapper[_A, _B, _C, _D]: ...
# no template, no role
@overload
def EndpointWrapper(
    charm: CharmBase,
    relation_name: str,
    template: None = None,
    role: None = None,
    validator: Optional[Type[_Validator]] = None,
    on_joined: Optional[Callable] = None,
    on_changed: Optional[Callable] = None,
    on_broken: Optional[Callable] = None,
    on_departed: Optional[Callable] = None,
    on_created: Optional[Callable] = None
) -> _EndpointWrapper: ...

@overload
def Template(
    provider: _DMProv,
    requirer: _DMReq,
) -> _Template[_DMProv, _DMReq]: ...
@overload
def Template(
    provider: _DMProv,
) -> _Template[_DMProv, _DataBagModel[None, None]]: ...
@overload
def Template(
    requirer: _DMReq,
) -> _Template[_DataBagModel[None, None], _DMReq]: ...
@overload
def Template() -> _Template[_DataBagModel[None, None], _DataBagModel[None, None]]: ...

def _get_dataclass_defaults(model:Any) -> Dict[str, Any]: ...
def _get_pydantic_defaults(model:Any) -> Dict[str, Any]: ...