"""Relation wrapper for Charms."""

import collections
import dataclasses
import json
import logging
from dataclasses import MISSING, Field, dataclass, is_dataclass
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    Mapping,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from ops.charm import CharmBase
from ops.framework import Object
from ops.model import Application
from ops.model import Model as OpsModel
from ops.model import Relation as OpsRelation
from ops.model import Unit
from typing_extensions import Literal, Protocol

logger = logging.getLogger(__name__)

_T = TypeVar("_T")
M = TypeVar("M")

Model = Any  # dataclass or pydantic model
ModelName = Literal["local_app", "remote_app", "local_unit", "remote_unit"]
Models = Mapping[ModelName, Optional[Any]]
UnitOrApplication = Union[Unit, Application]


@dataclass
class DataBagModel:
    """Databag model."""

    app: Type[Model] = None
    unit: Type[Model] = None

    def to_dict(self) -> dict:
        """Convert to dict."""

        def _to_dict(cls: Type):
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

        return {"app": self.app.to_dict(), "unit": self.app.to_dict()}


@dataclass
class Template:
    """Data template for requirer and provider sides of an integration."""

    requirer: DataBagModel = None
    provider: DataBagModel = None

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
            "requirer": self.requirer.to_dict(),
            "provider": self.provider.to_dict(),
        }


@dataclass
class RelationModel:
    """Model of a relation as seen from either side of it."""

    local_app_data_model: Type[Model] = None
    remote_app_data_model: Type[Model] = None
    local_unit_data_model: Type[Model] = None
    remote_unit_data_model: Type[Model] = None

    @staticmethod
    def from_charm(
        charm: CharmBase, relation_name: str, template: Template
    ) -> "RelationModel":
        """Guess the model from a charm's meta and a template."""
        if not template:
            # empty template --> empty model
            return RelationModel()
        if relation_name in charm.meta.requires:
            return template.as_requirer_model()
        return template.as_provider_model()

    def get(self, name):
        """Get a specific data model by name."""
        return getattr(self, name + "_data_model")


class ValidationError(RuntimeError):
    """Error validating the data."""


class CoercionError(ValidationError):
    """Error coercing the data into its specified type."""


class InvalidFieldNameError(ValidationError):
    """The specified field is not declared in the model."""


class CannotWriteError(RuntimeError):
    """Insufficient permissions to write to the databag."""


class _Validator(Protocol):
    model: Model

    def validate(self, data: dict, _raise: bool = False) -> bool:
        pass

    def check_field(self, key) -> Any:
        pass

    def deserialize(self, key, value) -> Any:
        pass

    def serialize(self, key, value) -> str:
        pass


def _loads(method):
    @wraps(method)
    def wrapper(self: "PydanticValidator", *args, **kwargs):
        if not self._loaded:
            self._load()
        return method(self, *args, **kwargs)

    return wrapper


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

    def validate(self, data: dict, _raise: bool = False):
        """Full schema validation: check data matches model."""
        model = self.model
        if not model:  # no model --> all data is valid
            return True

        err = False

        for key, value in data.items():
            try:
                field: Field = self.check_field(key)
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
                    f"{key} can't be cast to the expected type {field.type}; "
                    f"value={value}; error={e}; this could be a spurious "
                    f"error if you are trying to use complex datatypes."
                )
                err = True

        missing_data = False
        for name, field in model.__dataclass_fields__.items():
            if name not in data and field.default is MISSING:
                missing_data = True

        if missing_data:
            # could be that there are errors AND some data is missing;
            # in this case we assume it's incomplete = missing takes precedence
            return None

        if err:
            if _raise:
                raise ValidationError(self.model, data)
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
        field = self.check_field(key)
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

        return json.dumps(value)

    def deserialize(self, key: str, value: str) -> Any:
        """Cast back databag content to its intended type."""
        if not self.model:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.error("unable to decode {}; returning it raw.".format(value))
                return value

        field = self.check_field(key)
        try:
            return self._parse_obj_as(value, field.type)
        except Exception as e:
            logger.error(e)
            raise CoercionError(key, value, field.type) from e


class PydanticValidator:
    """Validate data based on pydantic models.

    Requires pydantic to be installed.
    """

    _BaseModel = None
    _PydanticValidationError = None
    _parse_obj_as = None
    _parse_raw_as = None
    _loaded = False

    _model = None

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
        self._PydanticValidationError = ValidationError
        self._parse_obj_as = parse_obj_as
        self._parse_raw_as = parse_raw_as
        self._loaded = True

    @_loads
    def validate(self, data: dict, _raise: bool = False):
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
                if _raise:
                    raise ValidationError(self.model, data)
                return False
            return None

        return True

    @_loads
    def check_field(self, name):
        """Verify that `name` is a valid field in the schema."""
        if not self.model:
            return None

        field = self.model.__fields__.get(name)
        if not field:
            raise InvalidFieldNameError(name)
        return field

    @_loads
    def coerce(self, key, value):
        """Coerce obj to the given field."""
        field = self.check_field(key)
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

        field = self.check_field(obj)
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
        self._model: OpsModel = charm.model
        self._local_unit: Unit = charm.unit
        self._local_app: Application = charm.app
        self._is_leader: bool = charm.unit.is_leader()

    @property
    def local_unit(self) -> Unit:
        return self._local_unit

    @property
    def local_app(self) -> Application:
        return self._local_app


def _needs_write_permission(method):
    @wraps(method)
    def wrapper(self: "DataWrapper", *args, **kwargs):
        if not self.can_write:
            raise CannotWriteError(self._relation, self._entity)
        return method(self, *args, **kwargs)

    return wrapper


class DataWrapper(Generic[M], collections.abc.MutableMapping):
    """Wrapper for the databag of a specific entity involved in a relation."""

    def __init__(
        self,
        relation: OpsRelation,
        entity: UnitOrApplication,
        model: Model,
        validator: _Validator,
        can_write: bool = False,
    ):
        self._relation = relation
        self._data = relation.data[entity]

        self._validator = validator
        validator.model = model

        self._entity = entity
        self._model = model
        self.can_write = can_write

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, item):
        self._validator.check_field(item)
        value = self._data[item]
        # coerce value to the type specified by the field
        obj = self._validator.deserialize(item, value)
        return obj

    @_needs_write_permission
    def __setitem__(self, key, value):
        self._validator.check_field(key)

        # we can only do validation if all mandatory fields have been set already,
        # and the user might be doing something like
        # relation_data['key'] = 'value'
        # --> required 'keyB' is not set yet! cannot validate yet
        # relation_data['keyB'] = 'valueB'
        # --> now we can validate; only now we can find out whether 'key' is valid.
        value = self._validator.serialize(key, value)
        self._data[key] = value

    @_needs_write_permission
    def __delitem__(self, key):
        self._validator.check_field(key)
        self._data[key] = ""

    def __eq__(self, other):
        return self._data == other

    def __bool__(self):
        return bool(self._data)

    @property
    def valid(self) -> Optional[bool]:
        """Whether this databag as a whole is valid."""
        return self._validator.validate(self._data)

    def validate(self):
        """Validate the databag and raise if not valid."""
        self._validator.validate(self._data, _raise=True)

    def __repr__(self):
        validity = self.valid
        valid_str = (
            "valid" if validity else ("invalid" if validity is False else "unfilled")
        )
        return (
            f"<{self._relation.name}[{type(self._entity).__name__}:: "
            f"{self._entity.name}] {repr(self._data)} "
            f"({valid_str})>"
        )


class Relation(_RelationBase):
    """Encapsulates the relation between the local unit and a single remote unit.

    Usage:
    >>> def on_event(self, _event):
    >>>     relation = Relation(self, self._relation, self._model)
    >>>     foo = relation.remote_app_data['foo']
    >>>     relation.local_app_data['bar'] = foo + 1
    >>>     assert relation.local_app_valid
    """

    def __init__(
        self,
        charm: CharmBase,
        relation: OpsRelation,
        model: RelationModel,
        validator: Type[_Validator] = DEFAULT_VALIDATOR,
    ):
        super().__init__(charm=charm, relation_name=relation.name, model=model)
        self._validator = validator()
        self._relation = relation
        self._remote_units: Tuple[Unit] = tuple(relation.units)
        self._remote_app: Application = relation.app

    def wraps(self, relation: OpsRelation):
        """Check if this Relation wraps the provided ops.Relation object."""
        return relation is self._relation

    @property
    def relation(self) -> OpsRelation:
        """Get the underlying `ops.Relation` object."""
        return self._relation

    @property
    def remote_units(self) -> Tuple[Unit]:
        """Get the remote units."""
        return self._remote_units

    @property
    def remote_app(self) -> Application:
        """Get the remote application object."""
        return self._remote_app

    @property
    def remote_units_valid(self) -> Optional[bool]:
        """Whether the `remote_units` side of this relation is valid."""
        return get_worst_case(
            (ru_data.valid for ru_data in self.remote_units_data.values())
        )

    @property
    def remote_app_valid(self) -> Optional[bool]:
        """Whether the `remote_app` side of this relation is valid."""
        return self.remote_app_data.valid

    @property
    def local_unit_valid(self) -> Optional[bool]:
        """Whether the `local_unit` side of this relation is valid."""
        return self.local_unit_data.valid

    @property
    def local_app_valid(self) -> Optional[bool]:
        """Whether the `local_app` side of this relation is valid."""
        return self.local_app_data.valid

    @property
    def local_valid(self) -> Optional[bool]:
        """Whether the `local` side of this relation is valid."""
        return get_worst_case((self.local_app_valid, self.local_unit_valid))

    @property
    def remote_valid(self) -> Optional[bool]:
        """Whether the `remote` side of this relation is valid."""
        return get_worst_case((self.remote_app_valid, self.remote_units_valid))

    @property
    def valid(self) -> Optional[bool]:
        """Whether this relation as a whole is valid."""
        return get_worst_case((self.local_valid, self.remote_valid))

    def _wrap_data(
        self, entity: UnitOrApplication, model_name: ModelName, can_write=False
    ) -> DataWrapper[Any]:
        return DataWrapper(
            relation=self._relation,
            entity=entity,
            model=self._relation_model.get(model_name),
            validator=self._validator,
            can_write=can_write,
        )

    @property
    def local_app_data(self) -> DataWrapper[Any]:
        """Get the data from the `local_app` side of the relation."""
        return self._wrap_data(self._local_app, "local_app", can_write=self._is_leader)

    @property
    def remote_app_data(self) -> DataWrapper[Any]:
        """Get the data from the `remote_app` side of the relation."""
        return self._wrap_data(self._remote_app, "remote_app")

    @property
    def local_unit_data(self) -> DataWrapper[Any]:
        """Get the data from the `local_unit` side of the relation."""
        return self._wrap_data(self._local_unit, "local_unit", can_write=True)

    @property
    def remote_units_data(self) -> Mapping[Unit, DataWrapper[Any]]:
        """Get the data from the `remote_units` side of the relation."""
        return {
            remote_unit: self._wrap_data(remote_unit, "remote_unit")
            for remote_unit in self._remote_units
        }


def get_worst_case(validity: Iterable[Optional[bool]]) -> Optional[bool]:
    """Get the worst of (from bad to worse): True, None, False."""
    out = True
    for value in validity:
        if value is None and out is True:  # True --> None
            out = value
        if value is False and out in {None, True}:  # {None/True} --> False
            out = value
    return out


class Relations(_RelationBase, Object):
    """Encapsulates the relation between the local application and a remote one.
    Usage:

    >>> class MyDataModel(Model):
    >>>     foo: int
    >>>     bar: str
    >>>     baz: SomeOtherModel  # noqa
    >>> class MyCharm(CharmBase):
    >>>     def __init__(self, *args):
    >>>         super().__init__(*args)
    >>>         self._ingress_relations = ingress = Relations(
    ...             self, 'ingress',
    ...             local_app_data_model=MyDataModel,
    ...             on_joined=self._on_ingress_joined,
    ...         )
    >>>     def _on_ingress_joined(self, event, relation:Relation):
    >>>         if relation.remote_valid:
    >>>             # remote apps in the clear!
    >>>             self.do_stuff()  # noqa
    >>>         if relation.valid:
    >>>             # all clear!
    >>>             self.do_stuff()  # noqa
    """

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        template: Template = None,
        validator: Type[_Validator] = DEFAULT_VALIDATOR,
        on_joined: Callable = None,
        on_changed: Callable = None,
        on_broken: Callable = None,
        on_departed: Callable = None,
        on_created: Callable = None,
    ):
        """Initialize."""
        model = RelationModel.from_charm(charm, relation_name, template)
        _RelationBase.__init__(self, charm, relation_name, model=model)
        Object.__init__(self, charm, relation_name + "_wrapper")
        self._validator = validator

        # register all provided event handlers
        event_handlers = {
            "relation_joined": on_joined,
            "relation_changed": on_changed,
            "relation_broken": on_broken,
            "relation_departed": on_departed,
            "relation_created": on_created,
        }

        for name, handler in event_handlers.items():
            if not handler:
                continue
            event = getattr(charm.on[relation_name], name)
            charm.framework.observe(event, handler)

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

    def wrap(self, relation: OpsRelation) -> Relation:
        """Get the Relation wrapper object from an ops Relation object."""
        return next(filter(lambda R: R.wraps(relation), self.relations))

    @property
    def _relations(self) -> Tuple[OpsRelation, ...]:
        relations = self._model.relations.get(self._relation_name)
        return tuple(relations) if relations else ()

    @property
    def relations(self) -> Tuple[Relation]:
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

    @property
    def remote_units_valid(self):
        """Whether the `remote_units` side of this relation is valid."""
        return get_worst_case(r.remote_units_valid for r in self.relations)

    @property
    def remote_apps_valid(self):
        """Whether the `remote_apps` side of this relation is valid."""
        return get_worst_case(r.remote_app_valid for r in self.relations)

    @property
    def local_unit_valid(self):
        """Whether the `local_unit` side of this relation is valid."""
        if not self.relations:
            return True
        return get_worst_case(map(lambda r: r.local_unit_valid, self.relations))

    @property
    def local_app_valid(self):
        """Whether the `local_app` side of this relation is valid."""
        if not self.relations:
            return True
        return get_worst_case(map(lambda r: r.local_app_valid, self.relations))

    @property
    def remote_valid(self):
        """Whether the `remote` side of this relation is valid."""
        return get_worst_case(map(lambda r: r.remote_valid, self.relations))

    @property
    def local_valid(self):
        """Whether the `local` side of this relation is valid."""
        return get_worst_case(map(lambda r: r.local_valid, self.relations))

    @property
    def valid(self):
        """Whether this relation as a whole is valid."""
        return get_worst_case(map(lambda r: r.valid, self.relations))

    @property
    def local_app_data(self) -> Dict[Application, DataWrapper[Any]]:
        """Map remote apps to the `local_app` side of the relation."""
        if not self.relations:
            return {}
        return {r.remote_app: r.local_app_data for r in self.relations}

    @property
    def remote_apps_data(self) -> Dict[Application, DataWrapper[Any]]:
        """Get the data from the `remote_apps` side of the relation."""
        return {r.remote_app: r.remote_app_data for r in self.relations}

    @property
    def local_unit_data(self) -> Dict[Application, DataWrapper[Any]]:
        """Map remote apps to the `local_unit` side of the relation."""
        if not self.relations:
            return {}
        return {r.remote_app: r.local_unit_data for r in self.relations}

    @property
    def remote_units_data(self) -> Dict[Unit, DataWrapper[Any]]:
        """Get the data from the `remote_units` side of the relation."""
        data = {}
        for r in self.relations:
            data.update(r.remote_units_data)
        return data

    @staticmethod
    def _publish_defaults(data: DataWrapper[Any]):
        """Write the databags with the template defaults."""
        if isinstance(data, dict):
            return

        assert data.can_write
        if model := data._model:
            defaults = get_defaults(model)
            for key, value in defaults.items():
                data[key] = value


def get_defaults(model):
    """Get all defaulted fields from the model."""
    # TODO Handle recursive models.
    if is_dataclass(model):
        return _get_dataclass_defaults(model)
    else:
        return _get_pydantic_defaults(model)


def _get_dataclass_defaults(model):
    return {
        field.name: field.default
        for field in model.__dataclass_fields__.values()
        if field.default is not dataclasses.MISSING
    }


def _get_pydantic_defaults(model):
    return {
        field.name: field.default
        for field in model.__fields__.values()
        if field.default
    }
