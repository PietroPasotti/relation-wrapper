import collections
import dataclasses
import json
import logging
import typing
from dataclasses import MISSING, Field, dataclass, is_dataclass
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from ops.charm import CharmBase, RelationEvent
from ops.framework import Object

if typing.TYPE_CHECKING:
    from typing import Protocol

    from ops.model import Application
    from ops.model import Model as OpsModel
    from ops.model import Relation as OpsRelation
    from ops.model import RelationDataContent, Unit

    # fmt: off
    Role = Literal["requirer", "provider"]
    Model = Any  # dataclass or pydantic model
    ModelName = Literal["local_app", "remote_app", "local_unit", "remote_unit"]
    Models = Mapping[ModelName, Optional[Model]]
    UnitOrApplication = Union["Unit", "Application"]

    class _Validator(Protocol):
        _parse_obj_as: Callable[[Type, Any], str]
        _parse_raw_as: Callable[[Type, str], Any]
        _model: Any
        model: Model
        def validate(self, data: Mapping, _raise: bool = False) -> bool: ...  # type: ignore
        def check_field(self, key: str) -> Any: ...  # type: ignore
        def deserialize(self, key: str, value: str) -> Any: ...  # type: ignore
        def serialize(self, key: str, value: Any) -> str: ...  # type: ignore
    # fmt: on

logger = logging.getLogger(__name__)

_ROLE_MISMATCH_WARN = "you declared a {}_template for relation {}, but this charm's metadata says that the role for this relation should be: {}"

_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")
_D = TypeVar("_D")
_T = TypeVar("_T")

_DMReq = TypeVar("_DMReq", bound="_DataBagModel[Any, Any]")
_DMProv = TypeVar("_DMProv", bound="_DataBagModel[Any, Any]")
_RelationModel = TypeVar("_RelationModel", bound="RelationModel")


@dataclass
class _DataBagModel(Generic[_A, _B]):
    """Databag model."""

    app: Optional[_A] = None
    unit: Optional[_B] = None

    def to_dict(self) -> dict:
        """Convert to dict."""

        def _to_dict(cls: Optional[Model]):
            if cls is None:
                return None
            try:
                import pydantic

                if isinstance(cls, pydantic.BaseModel):
                    return cls.dict()
            except ModuleNotFoundError:
                pass

            if is_dataclass(cls):
                dct = {}
                for field_name, field in cls.__dataclass_fields__.items():
                    if is_dataclass(field.type):
                        serialized = _to_dict(field.type)
                    else:
                        serialized = str(field.type.__name__)
                    dct[field_name] = serialized
                return dct

            raise TypeError(f"Cannot serialize {cls}")

        return {"app": _to_dict(self.app), "unit": _to_dict(self.unit)}


# fmt: off
@overload
def DataBagModel(*, app: _A, unit: _B) -> _DataBagModel[_A, _B]: ...
@overload
def DataBagModel(*, app: _A) -> _DataBagModel[_A, None]: ...
@overload
def DataBagModel(*, unit: _B) -> _DataBagModel[None, _B]: ...
# fmt: on


def DataBagModel(*, app: Optional["Model"] = None, unit: Optional["Model"] = None):
    """Databag model."""
    return _DataBagModel(app, unit)


@dataclass
class _Template(Generic[_DMProv, _DMReq]):
    """Data template for requirer and provider sides of an integration."""

    provider: Optional[_DMProv] = None
    requirer: Optional[_DMReq] = None

    def as_requirer_model(self) -> "RelationModel":
        """Get the template as seen from the requirer side."""
        return RelationModel(
            local_app_data_model=self.requirer.app if self.requirer else None,
            local_unit_data_model=self.requirer.unit if self.requirer else None,
            remote_app_data_model=self.provider.app if self.provider else None,
            remote_unit_data_model=self.provider.unit if self.provider else None,
        )

    def as_provider_model(self) -> "RelationModel":
        """Get the template as seen from the provider side."""
        return RelationModel(
            local_app_data_model=self.provider.app if self.provider else None,
            local_unit_data_model=self.provider.unit if self.provider else None,
            remote_app_data_model=self.requirer.app if self.requirer else None,
            remote_unit_data_model=self.requirer.unit if self.requirer else None,
        )

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {
            "requirer": self.requirer.to_dict() if self.requirer else None,
            "provider": self.provider.to_dict() if self.provider else None,
        }


# fmt: off
@overload
def Template(*, provider: _DMProv, requirer: _DMReq) -> _Template[_DMProv, _DMReq]: ...
@overload
def Template(*, provider: _DMProv) -> _Template[_DMProv, _DataBagModel[None, None]]: ...
@overload
def Template(*, requirer: _DMReq) -> _Template[_DataBagModel[None, None], _DMReq]: ...
@overload
def Template() -> _Template[_DataBagModel[None, None], _DataBagModel[None, None]]: ...
# fmt: on


def Template(  # noqa: N802
    *,
    provider: Optional[_DMProv] = None,
    requirer: Optional[_DMReq] = None,
) -> _Template[_DMProv, _DMReq]:
    """Data template for requirer and provider sides of a relation."""  # noqa: D401
    return _Template(provider=provider, requirer=requirer)


@dataclass
class RelationModel(Generic[_A, _B, _C, _D]):
    """Model of a relation as seen from either side of it."""

    local_app_data_model: Optional[_A] = None
    remote_app_data_model: Optional[_B] = None
    local_unit_data_model: Optional[_C] = None
    remote_unit_data_model: Optional[_D] = None

    @staticmethod
    def from_charm(
        charm: CharmBase,
        relation_name: str,
        template: Optional[_Template] = None,
        role: str = "unknown",
    ) -> "RelationModel":
        """Guess the model from a charm's meta and a template."""
        if not template:
            # empty template --> empty model
            return RelationModel()
        if relation_name in charm.meta.requires:
            if role == "provider":
                logger.warning(
                    _ROLE_MISMATCH_WARN.format(role, relation_name, "requirer")
                )
            return template.as_requirer_model()
        if role == "requirer":
            logger.warning(_ROLE_MISMATCH_WARN.format(role, relation_name, "provider"))
        return template.as_provider_model()

    def get(self, name: str) -> Union[_A, _B, _C, _D]:
        """Get a specific data model by name."""
        return getattr(self, name + "_data_model")


class EndpointError(RuntimeError):
    """Base class for errors raised from this library."""


class ValidationError(EndpointError):
    """Error validating the data."""


class CoercionError(ValidationError):
    """Error coercing the data into its specified type."""


class InvalidFieldNameError(ValidationError):
    """The specified field is not declared in the model."""


class CannotWriteError(EndpointError):
    """Insufficient permissions to write to the databag."""


class UnboundEndpointError(EndpointError):
    """Raised when an unbound endpoint is asked to access the current relation."""


class TooManyRelations(EndpointError):
    """Raised when a SingularEndpoint has more than 1 relations."""

    def __init__(self, relation_name: str) -> None:
        super().__init__(f"Too many relations bound to {relation_name}")


def _loads(method):
    @wraps(method)
    def wrapper(self: "PydanticValidator", *args, **kwargs):
        if not self._loaded:
            self._load()
        return method(self, *args, **kwargs)

    return wrapper


# TODO: consider removing the dataclass validation logic and say:
#  want validation? do pydantic. Otherwise it's a wormhole + reinventing the wheel.
class DataclassValidator:
    """Validates data based on a dataclass model."""

    _model = None

    @property
    def model(self):
        """Get the dataclass type."""
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    @staticmethod
    def _parse_obj_as(obj, type_):
        try:
            return type_(obj)
        except:  # noqa
            logger.error(f"cannot cast {obj} to {type_}; giving up...")
            raise

    def validate(self, data: dict):
        """Full schema validation: check data matches model."""
        model = self.model
        if not model:  # no model --> all data is valid
            return True

        err = False

        for key, value in data.items():
            try:
                field: Optional[Field] = self.check_field(key)
            except InvalidFieldNameError as e:
                logger.error(
                    f"{key} is an invalid field name; value={value}; error={e}"
                )
                err = True
                continue
            try:
                self.deserialize(key, value)
            except CoercionError as e:
                logger.error(
                    f"{key} can't be cast to the expected field {field}; "
                    f"value={value}; error={e}; this could be a spurious "
                    f"error if you are trying to use complex datatypes."
                )
                err = True

        missing_data = False
        for name, field in model.__dataclass_fields__.items():
            if name not in data and field.default is MISSING:  # type: ignore
                missing_data = True

        if missing_data:
            # could be that there are errors AND some data is missing;
            # in this case we assume it's incomplete = missing takes precedence
            return None

        if err:
            return False
        return True

    def check_field(self, name):
        """Verify that `name` is a valid field in the schema."""
        if not self.model:
            return None
        field = self.model.__dataclass_fields__.get(name)
        if not field:
            raise InvalidFieldNameError(name)
        return field

    def serialize(self, key, value) -> str:
        """Convert to string."""
        if not self.model:
            if isinstance(value, str):
                return value
            return json.dumps(value)

        # check that the key is a valid field
        field: Any = self.check_field(key)
        # check that the field type matches the type of the object we're dumping;
        # otherwise we won't be able to deserialize it later.
        if not isinstance(value, field.type):
            raise CoercionError(
                "cannot encode {} : {}, expected {}".format(key, value, field.type)
            )
        # dump
        from dataclasses import asdict, is_dataclass

        if is_dataclass(value):
            return json.dumps(asdict(value))

        return str(value)

    def deserialize(self, key: str, value: str) -> Any:
        """Cast back databag content to its intended type."""
        if not self.model:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.error("unable to decode {}; returning it raw.".format(value))
                return value

        field: Any = self.check_field(key)
        try:
            return self._parse_obj_as(value, field.type)
        except Exception as e:
            logger.error(e)
            raise CoercionError(key, value, field.type) from e


class PydanticValidator:
    """Validate data based on pydantic models.

    Requires pydantic to be installed.
    """

    if typing.TYPE_CHECKING:
        _BaseModel: Type
        _PydanticValidationError: Type[BaseException]

    _loaded: bool = False
    _model: Any = None

    @property
    def model(self):
        """Get the pydantic model."""
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    def _load(self):
        try:
            from pydantic import BaseModel, ValidationError, parse_obj_as, parse_raw_as
        except ModuleNotFoundError:
            raise RuntimeError("this validator requires `pydantic`")

        self._BaseModel = BaseModel
        self._PydanticValidationError: Type[BaseException] = ValidationError
        self._parse_obj_as = parse_obj_as
        self._parse_raw_as = parse_raw_as
        self._loaded = True

    @_loads
    def validate(self, data: dict):
        """Full schema validation: check data matches model."""
        if not self.model:  # no model --> all data is valid
            return True

        err = False
        try:
            self.model.validate(data)
        except self._PydanticValidationError as e:
            logger.debug(e)
            err = True

        if err:
            if data:
                return False
            return None

        return True

    @_loads
    def check_field(self, name):
        """Verify that `name` is a valid field in the schema."""
        if not self.model:
            return None

        field: Any = self.model.__fields__.get(name)
        if not field:
            raise InvalidFieldNameError(name)
        return field

    @_loads
    def coerce(self, key, value):
        """Coerce obj to the given field."""
        field: Any = self.check_field(key)
        try:
            return self._parse_obj_as(field.type_, value)
        except self._PydanticValidationError as e:
            logger.error(e)
            raise CoercionError(key, value, field.type_)

    @_loads
    def serialize(self, key, value) -> str:
        """Convert value to string."""
        if not self.model:
            return json.dumps(value)

        # check that the key is a valid field
        self.check_field(key)
        # check that the field type matches the value
        self.coerce(key, value)
        # dump
        if isinstance(value, self._BaseModel):
            return value.json()
        elif isinstance(value, str):
            return value
        else:
            return json.dumps(value)

    @_loads
    def deserialize(self, obj: str, value: str) -> Any:
        """Cast databag contents back to its model-given type."""
        if not self.model:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.error("unable to decode {}; returning it raw.".format(value))
                return value

        field: Any = self.check_field(obj)
        if isinstance(value, field.type_):
            return value
        return self._parse_raw_as(field.type_, value)


def _get_default_validator():
    try:
        import pydantic  # noqa

        return PydanticValidator
    except ModuleNotFoundError:
        return DataclassValidator


DEFAULT_VALIDATOR = _get_default_validator()


class _RelationBase:
    def __init__(self, charm: CharmBase, relation_name: str, model: RelationModel):
        self._charm = charm
        self._relation_name = relation_name
        self._relation_model = model
        self._model: "OpsModel" = charm.model
        self._local_unit: "Unit" = charm.unit
        self._local_app: "Application" = charm.app
        self._is_leader: bool = charm.unit.is_leader()

    @property
    def local_unit(self) -> "Unit":
        return self._local_unit

    @property
    def local_app(self) -> "Application":
        return self._local_app


def _needs_write_permission(method):
    @wraps(method)
    def wrapper(self: "DataWrapper", *args, **kwargs):
        params = self.__datawrapper_params__
        if not params.can_write:
            raise CannotWriteError(params.relation, params.entity)
        return method(self, *args, **kwargs)

    return wrapper


@dataclass
class DataWrapperParams(Generic[_T]):  # noqa: D101
    relation: "OpsRelation"
    data: "RelationDataContent"
    validator: "_Validator"
    entity: "UnitOrApplication"
    model: _T
    can_write: bool


class DataWrapper(Generic[_T], collections.abc.MutableMapping):  # type: ignore
    """Wrapper for the databag of a specific entity involved in a relation."""

    if typing.TYPE_CHECKING:
        __datawrapper_params__: DataWrapperParams[_T]

    def __init__(
        self,
        relation: "OpsRelation",
        entity: "UnitOrApplication",
        model: "Model",
        validator: "_Validator",
        can_write: bool = False,
    ):

        # fixme: potential dedup issue here; externalize model in Validator.
        validator.model = model
        # keep the namespace clean: everything we put here is a name the user can't use
        self.__dict__["__datawrapper_params__"] = DataWrapperParams(
            relation=relation,
            data=relation.data[entity],
            validator=validator,
            entity=entity,
            model=model,
            can_write=can_write,
        )

    def __iter__(self):
        return iter(self.__datawrapper_params__.data)

    def __len__(self):
        return len(self.__datawrapper_params__.data)

    def __getitem__(self, item):
        self.__datawrapper_params__.validator.check_field(item)
        value = self.__datawrapper_params__.data[item]
        # coerce value to the type specified by the field
        obj = self.__datawrapper_params__.validator.deserialize(item, value)
        return obj

    @_needs_write_permission
    def __setitem__(self, key, value):
        self.__datawrapper_params__.validator.check_field(key)

        # we can only do validation if all mandatory fields have been set already,
        # and the user might be doing something like
        # relation_data['key'] = 'value'
        # --> required 'keyB' is not set yet! cannot validate yet
        # relation_data['keyB'] = 'valueB'
        # --> now we can validate; only now we can find out whether 'key' is valid.
        value = self.__datawrapper_params__.validator.serialize(key, value)
        self.__datawrapper_params__.data[key] = value

    @_needs_write_permission
    def __delitem__(self, key):
        self.__datawrapper_params__.validator.check_field(key)
        self.__datawrapper_params__.data[key] = ""

    def __eq__(self, other):
        return self.__datawrapper_params__.data == other

    def __bool__(self):
        return bool(self.__datawrapper_params__.data)

    def __getattr__(self, item: str):
        return self[item]

    def __setattr__(self, key, value):
        self[key] = value

    def __repr__(self):
        validity = databag_valid(self)
        valid_str = (
            "valid" if validity else ("invalid" if validity is False else "unfilled")
        )
        params = self.__datawrapper_params__
        return (
            f"<{params.relation.name}[{type(params.entity).__name__}:: "
            f"{params.entity.name}] {repr(params.data)} "
            f"({valid_str})>"
        )


def databag_valid(data: DataWrapper) -> Optional[bool]:
    """Whether this databag as a whole is valid."""
    return data.__datawrapper_params__.validator.validate(
        data.__datawrapper_params__.data
    )


def validate_databag(data: DataWrapper):
    """Validate the databag and raise if not valid."""
    data.__datawrapper_params__.validator.validate(
        data.__datawrapper_params__.data, _raise=True
    )


class Relation(_RelationBase, Generic[_A, _B, _C, _D]):
    """Encapsulates the relation between the local unit and a single remote unit.

    Usage:
    >>> class MyCharm(CharmBase):
    >>>     def on_event(self, event):
    >>>         relation = Endpoint(self, "relation").wrap(event.relation)
    >>>         foo = relation.remote_app_data['foo']
    >>>         relation.local_app_data['bar'] = foo + 1
    >>>         assert relation._local_app_data_valid
    """

    def __init__(
        self,
        charm: CharmBase,
        relation: "OpsRelation",
        model: RelationModel,
        validator: Type = DEFAULT_VALIDATOR,
    ):
        super().__init__(charm=charm, relation_name=relation.name, model=model)
        self._validator_cls = validator
        self._relation = relation
        self._remote_units: Tuple["Unit"] = tuple(relation.units)  # type: ignore
        self._remote_app: "Application" = relation.app  # type: ignore

    def wraps(self, relation: "OpsRelation") -> bool:
        """Check if this Relation wraps the provided ops.Relation object."""
        return relation is self._relation

    @property
    def relation(self) -> "OpsRelation":
        """Get the underlying `ops.Relation` object."""
        return self._relation

    @property
    def remote_units(self) -> Tuple["Unit"]:
        """Get the remote units."""
        return self._remote_units

    @property
    def remote_app(self) -> "Application":
        """Get the remote application object."""
        return self._remote_app

    @staticmethod
    def _is_valid(data: Union[_A, _B, _C, _D]) -> Optional[bool]:
        # fixme: we need to ignore type here because mypy thinks data is _A
        #  while it is DataWrapper[_A]
        return databag_valid(data)  # type: ignore

    @property
    def _remote_units_data_valid(self) -> Optional[bool]:
        """Whether the `remote_units` side of this relation is valid."""
        return get_worst_case(
            (self._is_valid(ru_data) for ru_data in self.remote_units_data.values())
        )

    @property
    def _remote_app_data_valid(self) -> Optional[bool]:
        """Whether the `remote_app` side of this relation is valid."""
        return self._is_valid(self.remote_app_data)

    @property
    def _local_unit_data_valid(self) -> Optional[bool]:
        """Whether the `local_unit` side of this relation is valid."""
        return self._is_valid(self.local_unit_data)

    @property
    def _local_app_data_valid(self) -> Optional[bool]:
        """Whether the `local_app` side of this relation is valid."""
        return self._is_valid(self.local_app_data)

    @property
    def local_valid(self) -> Optional[bool]:
        """Whether the `local` side of this relation is valid."""
        return get_worst_case((self._local_app_data_valid, self._local_unit_data_valid))

    @property
    def remote_valid(self) -> Optional[bool]:
        """Whether the `remote` side of this relation is valid."""
        return get_worst_case(
            (self._remote_app_data_valid, self._remote_units_data_valid)
        )

    @property
    def valid(self) -> Optional[bool]:
        """Whether this relation as a whole is valid."""
        return get_worst_case((self.local_valid, self.remote_valid))

    def _wrap_data(
        self, entity: "UnitOrApplication", model_name: "ModelName", can_write=False
    ) -> DataWrapper[Any]:
        return DataWrapper(
            relation=self._relation,
            entity=entity,
            model=self._relation_model.get(model_name),
            validator=self._validator_cls(),
            can_write=can_write,
        )

    # FIXME: we don't have Proxy[T] yet, so we can't correctly type DataWrapper.
    #  therefore we pretend the return type is T.
    #  cfr: https://github.com/python/mypy/issues/5523
    @property
    def local_app_data(self) -> _A:  # real type: DataWrapper[_A]
        """Get the data from the `local_app` side of the relation."""
        return self._wrap_data(self._local_app, "local_app", can_write=self._is_leader)

    @property
    def local_unit_data(self) -> _B:  # real type: DataWrapper[_B]
        """Get the data from the `local_unit` side of the relation."""
        return self._wrap_data(self._local_unit, "local_unit", can_write=True)

    @property
    def remote_app_data(self) -> _C:  # real type: DataWrapper[_C]
        """Get the data from the `remote_app` side of the relation."""
        return self._wrap_data(self._remote_app, "remote_app")

    @property
    def remote_units_data(
        self,
    ) -> Mapping["Unit", _D]:  # real type: Mapping["Unit", DataWrapper[_D]]
        """Get the data from the `remote_units` side of the relation."""
        return {
            remote_unit: self._wrap_data(remote_unit, "remote_unit")
            for remote_unit in self._remote_units
        }


def get_worst_case(validity: Iterable[Optional[bool]]) -> Optional[bool]:
    """Get the worst of (from bad to worse): True, None, False."""
    out: Optional[bool] = True
    for value in validity:
        if value is None and out is True:  # True --> None
            out = value
        if value is False and out in {None, True}:  # {None/True} --> False
            out = value
    return out


class EndpointWrapper(_RelationBase, Object, Generic[_A, _B, _C, _D]):
    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        *,
        provider_template: Optional[_Template] = None,
        requirer_template: Optional[_Template] = None,
        validator: Type = DEFAULT_VALIDATOR,
        **kwargs,
    ):
        """Initialize."""
        if provider_template:
            role = "provider"
        elif requirer_template:
            role = "requirer"
        else:
            role = "unknown"
        if provider_template and requirer_template:
            raise TypeError("provide at most one of [provider|requirer]_template")

        template = provider_template or requirer_template

        model = RelationModel.from_charm(charm, relation_name, template, role=role)
        _RelationBase.__init__(self, charm, relation_name, model=model)
        Object.__init__(self, charm, relation_name + "_wrapper")
        self._validator = validator

        # register all provided event handlers
        self._event_handlers = event_handlers = {
            "relation_joined": kwargs.get("on_joined"),
            "relation_changed": kwargs.get("on_changed"),
            "relation_broken": kwargs.get("on_broken"),
            "relation_departed": kwargs.get("on_departed"),
            "relation_created": kwargs.get("on_created"),
        }

        charm.framework.observe(
            charm.on[relation_name].relation_created, self.publish_defaults
        )

    def publish_defaults(self, event):
        """Publish default unit and app data to local databags.

        Should be called once a relation is created.
        """
        relation = self.wrap(event.relation)
        if self._charm.unit.is_leader():
            self._publish_defaults(relation.local_app_data)
        self._publish_defaults(relation.local_unit_data)

    def wrap(self, relation: "OpsRelation") -> Relation[_A, _B, _C, _D]:
        """Get the Relation wrapper object from an ops.model.Relation object."""
        return Relation(
                charm=self._charm,
                relation=relation,
                model=self._relation_model,
                validator=self._validator,
            )

    @property
    def _relations(self) -> Tuple["OpsRelation", ...]:
        relations = self._model.relations.get(self._relation_name)
        return tuple(relations) if relations else ()

    @staticmethod
    def _publish_defaults(
        data: Union[_A, _B, _C, _D]
    ):  # real type: DataWrapper[Union[_A, _B, _C, _D]]
        """Write the databags with the template defaults."""
        if isinstance(data, dict):  # fixme: hacky
            return

        data = typing.cast(DataWrapper, data)
        assert data.__datawrapper_params__.can_write
        if model := data.__datawrapper_params__.model:
            defaults = get_defaults(model)
            for key, value in defaults.items():
                data[key] = value

class _SingularEndpoint(EndpointWrapper[_A, _B, _C, _D]):
    """Wrapper for a single relation sharing an endpoint."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if len(self._relations) > 1:
            raise TooManyRelations(self._relation_name)

    @property
    def _relation(self) -> "OpsRelation":
        if not self._relations:
            raise UnboundEndpointError(self._relation_name)
        return self._relations[0]

    @property
    def relation(self) -> Relation[_A, _B, _C, _D]:
        """All relations currently alive on this charm."""
        return self.wrap(self._relation)

    @property
    def current(self):
        # for compatibility with _Endpoint
        return self.relation

    @property
    def _remote_units_data_valid(self):
        """Whether the `remote_units` side of this relation is valid."""
        return self.relation._remote_units_data_valid

    @property
    def _remote_apps_data_valid(self):
        """Whether the `remote_apps` side of this relation is valid."""
        return self.relation._remote_app_data_valid

    @property
    def _local_units_data_valid(self):
        """Whether the `local_unit` side of this relation is valid."""
        if not self.relation:
            return None
        return self.relation._local_unit_data_valid

    @property
    def _local_apps_data_valid(self):
        """Whether the `local_app` side of this relation is valid."""
        if not self.relation:
            return None
        return self.relation._local_app_data_valid

    @property
    def remote_valid(self):
        """Whether the `remote` side of this relation is valid."""
        if not self.relation:
            return None
        return self.relation.remote_valid

    @property
    def local_valid(self):
        """Whether the `local` side of this relation is valid."""
        if not self.relation:
            return None
        return self.relation.local_valid

    @property
    def valid(self):
        """Whether this relation as a whole is valid."""
        if not self.relation:
            return None
        return self.relation.valid

    @property
    def local_app_data(
        self,
    ) -> _A:  # real type: DataWrapper[_A]
        """Get the local application databag."""
        if not self.relation:
            return {}  # type: ignore
        return self.relation.local_app_data

    @property
    def local_unit_data(
        self,
    ) -> _B:  # real type: DataWrapper[_B]
        """Get the local unit databag."""
        if not self.relation:
            return {}  # type: ignore
        return self.relation.local_unit_data

    @property
    def remote_app_data(
        self,
    ) -> _C:  # real type: DataWrapper[_C]
        """Get the remote app's databag."""
        if not self.relation:
            return {}  # type: ignore
        return self.relation.remote_app_data

    @property
    def remote_units_data(
        self,
    ) -> Dict["Unit", _D]:  # real type: Dict["Unit", DataWrapper[_D]]
        """Get the data from the `remote_units` side of the relation.

        A mapping from remote units to their databags."""
        if not self.relation:
            return {}
        return dict(self.relation.remote_units_data)


class _Endpoint(EndpointWrapper[_A, _B, _C, _D]):
    """Wrapper for a group of relations sharing an endpoint."""
    _wrapped_event = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, handler in self._event_handlers.items():
            if not handler:
                continue
            event = getattr(self._charm.on[self._relation_name], name)
            self._charm.framework.observe(event, self._wrap_event)

    def _wrap_event(self, event: RelationEvent):
        """Assign event to self._wrapped_event and call the registered handler."""
        self._wrapped_event = event
        event_name: str = event.handle.kind
        for event_type in self._event_handlers:
            if event_name.endswith(event_type):
                handler = self._event_handlers.get(event_type)
                if not handler:
                    raise ValueError(f"handler not found for {event_type}")
                handler(event)
                break
        self._wrapped_event = None
    @property
    def current(self) -> Relation[_A, _B, _C, _D]:
        """Access the currently wrapped relation.

        Usage:
            >>> class MyCharm(CharmBase):
            >>>     def __init__(self, *args):
            >>>         super().__init__(*args)
            >>>         self._foo = Endpoint(
            ...             self, 'foo', on_joined=self._on_foo_joined
            ...         )
            >>>     def _on_foo_joined(self, event):
            >>>         relation: Relation = self._foo.current
            >>>         # equivalent to:
            >>>         relation: Relation = self._foo.wrap(event.relation)

        """
        if not self._wrapped_event:
            raise UnboundEndpointError(
                "unbound endpoint: you can access this attribute "
                "only within the context of a wrapped event"
            )
        return self.wrap(self._wrapped_event.relation)

    @property
    def relations(self) -> Tuple[Relation[_A, _B, _C, _D], ...]:
        """All relations currently alive on this charm."""
        return tuple(
            Relation(
                charm=self._charm,
                relation=r,
                model=self._relation_model,
                validator=self._validator,
            )
            for r in self._relations
        )

    def __iter__(self) -> Iterator[Relation[_A, _B, _C, _D]]:
        yield from self.relations

    @property
    def _remote_units_data_valid(self):
        """Whether the `remote_units` side of this relation is valid."""
        if not self.relations:
            return None
        return get_worst_case(r._remote_units_data_valid for r in self.relations)

    @property
    def _remote_apps_data_valid(self):
        """Whether the `remote_apps` side of this relation is valid."""
        if not self.relations:
            return None
        return get_worst_case(r._remote_app_data_valid for r in self.relations)

    @property
    def _local_units_data_valid(self):
        """Whether the `local_unit` side of this relation is valid."""
        if not self.relations:
            return None
        return get_worst_case(map(lambda r: r._local_unit_data_valid, self.relations))

    @property
    def _local_apps_data_valid(self):
        """Whether the `local_app` side of this relation is valid."""
        if not self.relations:
            return None
        return get_worst_case(map(lambda r: r._local_app_data_valid, self.relations))

    @property
    def remote_valid(self):
        """Whether the `remote` side of this relation is valid."""
        if not self.relations:
            return None
        return get_worst_case(map(lambda r: r.remote_valid, self.relations))

    @property
    def local_valid(self):
        """Whether the `local` side of this relation is valid."""
        if not self.relations:
            return None
        return get_worst_case(map(lambda r: r.local_valid, self.relations))

    @property
    def valid(self):
        """Whether this relation as a whole is valid."""
        if not self.relations:
            return None
        return get_worst_case(map(lambda r: r.valid, self.relations))

    @property
    def local_apps_data(
        self,
    ) -> Dict["Application", _A]:  # real type: Dict["Application", DataWrapper[_A]]
        """Map remote apps to the `local_app` side of the relation."""
        if not self.relations:
            return {}
        return {r.remote_app: r.local_app_data for r in self.relations}

    @property
    def local_units_data(
        self,
    ) -> Dict["Unit", _B]:  # real type: Dict["Unit", DataWrapper[_B]]
        """Map remote apps to the `local_unit` side of the relation."""
        if not self.relations:
            return {}
        return {r.local_unit: r.local_unit_data for r in self.relations}

    @property
    def remote_apps_data(
        self,
    ) -> Dict["Application", _C]:  # real type: Dict["Application", DataWrapper[_C]]
        """Get the data from the `remote_apps` side of the relation."""
        if not self.relations:
            return {}
        return {r.remote_app: r.remote_app_data for r in self.relations}

    @property
    def remote_units_data(
        self,
    ) -> Dict["Unit", _D]:  # real type: Dict["Unit", DataWrapper[_D]]
        """Get the data from the `remote_units` side of the relation."""
        data: Dict["Unit", _D] = {}
        for r in self.relations:
            data.update(r.remote_units_data)
        return data


def get_defaults(model: Any) -> Dict[str, Any]:
    """Get all defaulted fields from the model."""
    # TODO Handle recursive models.
    if is_dataclass(model):
        return _get_dataclass_defaults(model)
    else:
        return _get_pydantic_defaults(model)


def _get_dataclass_defaults(model: Any) -> Dict[str, Any]:
    return {
        field.name: field.default
        for field in model.__dataclass_fields__.values()
        if field.default is not dataclasses.MISSING
    }


def _get_pydantic_defaults(model: Any) -> Dict[str, Any]:
    return {
        field.name: field.default
        for field in model.__fields__.values()
        if field.default
    }


# fmt: off
@overload
def SingularEndpoint(charm: CharmBase, relation_name: str, *, requirer_template: _Template[_DataBagModel[_A, _B], _DataBagModel[_C, _D]], validator: Optional[Type['_Validator']] = None, on_joined: Optional[Callable] = None, on_changed: Optional[Callable] = None, on_broken: Optional[Callable] = None, on_departed: Optional[Callable] = None, on_created: Optional[Callable] = None) -> _SingularEndpoint[_C, _D, _A, _B]: ...
# template and provider role
@overload
def SingularEndpoint(charm: CharmBase, relation_name: str, *, provider_template: _Template[_DataBagModel[_A, _B], _DataBagModel[_C, _D]], validator: Optional[Type['_Validator']] = None, on_joined: Optional[Callable] = None, on_changed: Optional[Callable] = None, on_broken: Optional[Callable] = None, on_departed: Optional[Callable] = None, on_created: Optional[Callable] = None) -> _SingularEndpoint[_A, _B, _C, _D]: ...
# no template, no role
@overload
def SingularEndpoint(charm: CharmBase, relation_name: str, *, template: None = None, validator: Optional[Type['_Validator']] = None, on_joined: Optional[Callable] = None, on_changed: Optional[Callable] = None, on_broken: Optional[Callable] = None, on_departed: Optional[Callable] = None, on_created: Optional[Callable] = None) -> _SingularEndpoint: ...

@overload
def Endpoint(charm: CharmBase, relation_name: str, *, requirer_template: _Template[_DataBagModel[_A, _B], _DataBagModel[_C, _D]], validator: Optional[Type['_Validator']] = None, on_joined: Optional[Callable] = None, on_changed: Optional[Callable] = None, on_broken: Optional[Callable] = None, on_departed: Optional[Callable] = None, on_created: Optional[Callable] = None) -> _Endpoint[_C, _D, _A, _B]: ...
# template and provider role
@overload
def Endpoint(charm: CharmBase, relation_name: str, *, provider_template: _Template[_DataBagModel[_A, _B], _DataBagModel[_C, _D]], validator: Optional[Type['_Validator']] = None, on_joined: Optional[Callable] = None, on_changed: Optional[Callable] = None, on_broken: Optional[Callable] = None, on_departed: Optional[Callable] = None, on_created: Optional[Callable] = None) -> _Endpoint[_A, _B, _C, _D]: ...
# no template, no role
@overload
def Endpoint(charm: CharmBase, relation_name: str, *, template: None = None, validator: Optional[Type['_Validator']] = None, on_joined: Optional[Callable] = None, on_changed: Optional[Callable] = None, on_broken: Optional[Callable] = None, on_departed: Optional[Callable] = None, on_created: Optional[Callable] = None) -> _Endpoint: ...
# fmt: on


def Endpoint(*args, **kwargs):  # noqa: N802
    """Encapsulates the relations between the local application and a remote one.
    Usage:

    >>> # make a dataclass, or inherit from pydantic.BaseModel
    >>> class MyDataModel:
    >>>     foo: int
    >>>     bar: str
    >>>     baz: SomeOtherModel  # noqa
    >>>
    >>> template = Template(provider=DataBagModel(app=MyDataModel))
    >>>
    >>> class MyCharm(CharmBase):
    >>>     def __init__(self, *args):
    >>>         super().__init__(*args)
    >>>         self._ingress = Endpoint(
    ...             self, 'ingress',
    ...             provider_template=template,
    ...             on_joined=self._on_ingress_joined,
    ...         )
    >>>     def _on_ingress_joined(self, event):
    >>>         relation = self._ingress.current
    >>>         if relation.remote_valid:
    >>>             # remote apps in the clear!
    >>>             self.do_stuff()  # noqa
    >>>         if relation.valid:
    >>>             # all clear!
    >>>             self.do_stuff()  # noqa
    """
    return _Endpoint(*args, **kwargs)


def SingularEndpoint(*args, **kwargs):  # noqa: N802
    """Encapsulates a single relation between the local application and a remote one.
    Usage:

    >>> # make a dataclass, or inherit from pydantic.BaseModel
    >>> class MyDataModel:
    >>>     foo: int
    >>>     bar: str
    >>>     baz: SomeOtherModel  # noqa
    >>>
    >>> template = Template(provider=DataBagModel(app=MyDataModel))
    >>>
    >>> class MyCharm(CharmBase):
    >>>     def __init__(self, *args):
    >>>         super().__init__(*args)
    >>>         self._ingress = SingularEndpoint(
    ...             self, 'ingress',
    ...             provider_template=template,
    ...             on_joined=self._on_ingress_joined,
    ...         )
    >>>     def _on_ingress_joined(self, event):
    >>>         relation = self._ingress
    >>>         if relation.remote_valid:
    >>>             # remote apps in the clear!
    >>>             self.do_stuff()  # noqa
    >>>         if relation.valid:
    >>>             # all clear!
    >>>             self.do_stuff()  # noqa
    """
    return _SingularEndpoint(*args, **kwargs)
