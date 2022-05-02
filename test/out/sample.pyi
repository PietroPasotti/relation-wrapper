from enum import Enum
from typing import Any, Literal

class DataBagModel:
    app: Any
    unit: Any
    def __init__(self, app: _A, unit: _U) -> None: ...

class Role(Enum):
    requirer: int
    provider: int

class Template:
    requirer: Any
    provider: Any
    def __init__(self, requirer: _DMReq, provider: _DMProv) -> None: ...

class RequirerAppModel:
    foo: int
    def __init__(self, foo) -> None: ...

class RequirerUnitModel: ...
class ProviderAppModel: ...

class ProviderUnitModel:
    bar: float
    def __init__(self, bar) -> None: ...

template: Any

class Relation:
    role_model: Any
    app: Any
    unit: Any
    def __init__(
        self, template: Template[_DMReq, _DMProv], role: Literal["requirer", "provider"]
    ) -> None: ...

relation: Any
app: RequirerAppModel
foo: Any
