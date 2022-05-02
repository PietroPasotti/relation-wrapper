from dataclasses import dataclass
from enum import Enum
from typing import Generic, Literal, Type, TypeVar, Union

_A = TypeVar("_A")
_U = TypeVar("_U")

_DMReq = TypeVar("_DMReq", bound="DataBagModel")
_DMProv = TypeVar("_DMProv", bound="DataBagModel")
_DM = TypeVar("_DM", bound="DataBagModel")


class DataBagModel(Generic[_A, _U]):
    def __init__(self, app: _A, unit: _U):
        self.app: _A = app
        self.unit: _U = unit


class Role(Enum):
    requirer = 1
    provider = 2


class Template(Generic[_DMReq, _DMProv]):
    def __init__(self, requirer: _DMReq, provider: _DMProv):
        self.requirer: _DMReq = requirer
        self.provider: _DMProv = provider


def make_template(requirer: DataBagModel, provider: DataBagModel) -> Template:
    return Template(requirer, provider)


class Relation:
    def __init__(self, app, unit):
        self.app = app
        self.unit = unit


def wrap_relation(
    template: Template, role: Literal["requirer", "provider"]
) -> Relation:
    if role == "requirer":
        return Relation(template.requirer.app, template.requirer.unit)
    else:
        return Relation(template.provider.app, template.provider.unit)
