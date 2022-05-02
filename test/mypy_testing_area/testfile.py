from dataclasses import dataclass

from sample import DataBagModel, Relation, Template, make_template, wrap_relation


@dataclass
class RequirerAppModel:
    foo: int


@dataclass
class RequirerUnitModel:
    pass


@dataclass
class ProviderAppModel:
    pass


@dataclass
class ProviderUnitModel:
    bar: float


template = make_template(
    requirer=DataBagModel(app=RequirerAppModel(foo=1), unit=RequirerUnitModel()),
    provider=DataBagModel(app=ProviderAppModel(), unit=ProviderUnitModel(bar=24.42)),
)

prov_relation = wrap_relation(template, "provider")
prov_app: ProviderUnitModel = prov_relation.unit

req_relation = wrap_relation(template, "requirer")
req_app: RequirerAppModel = req_relation.app
