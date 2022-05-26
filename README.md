# relation-wrapper

Provides high-level API to code relation interfaces with.

- Tested: Python 3.8+

## usage

The main idea of Endpoint is to make accessing (and reasoning about) 
relation data easier. The days of wondering 'is relation.app the provider, or the requirer app?'
are over.

```python
from ops import CharmBase
from endpoint_wrapper import Endpoint

class MyCharm(CharmBase):
    META = {'requires': {'foo': {'interface': 'bar'}}}

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Endpoint(
            self, 'foo',
            on_changed=self._on_foo_changed,
            on_joined=self._on_foo_joined,
        )
        
    def _on_foo_joined(self, _):
        unit_ips = []
        unit_codenames = []

        # grab some data from all related remote units (all 'foo' relations!)
        for relation in self.foo:
            for unit, unit_databag in relation.remote_units_data.items():
                unit_ips.append(unit_databag['IP'])
                unit_codenames.append(unit_databag['CODENAME'])
        
        # push it to all local application databags (all 'foo' relations!)
        for relation in self.foo:
            relation.local_app_data['unit_ips'] = str(unit_ips)
            relation.local_app_data['unit_codenames'] = str(unit_codenames)
        
    def _on_foo_changed(self, event):
        foo = self.foo.wrap(event.relation)  
        foo.local_app_data.cheese = 'cake'
        foo.local_app_data.rambo = 'film'
        assert foo.remote_app_data['arnold']['terminator'] == 42
```

## typing and validating

What if you want to type the contents of the databag?
What you typically have is, a relation interface is linked to four schemas:
 - a requirer app databag schema
 - a requirer unit databag schema (applies to all units)
 - a provider app databag schema
 - a provider unit databag schema (applies to all units)

We call the group of four schemas defining a relation its `Template`.
Usage:

```python
from pydantic import BaseModel
class RequirerAppModel(BaseModel):
    foo: int

class ProviderUnitModel(BaseModel):
    bar: float

# Alternatively, you can use dataclasses and things will work just the same
# (I think technically you can also mix the two, but it might need some testing)

from dataclasses import dataclass

@dataclass
class RequirerUnitModel:
    foo: str
    
@dataclass
class ProviderAppModel:
    bar: float

# Now let's define a template: that is, a spec of the shape of all 
# databags involved in the relation.

from endpoint_wrapper import Template, DataBagModel

template = Template(
    requirer=DataBagModel(
        app=RequirerAppModel, 
        unit=RequirerUnitModel
    ),
    provider=DataBagModel(
        app=ProviderAppModel, 
        unit=ProviderUnitModel
    )
)

# Now we can use the template in combination with the Endpoint:

from ops import CharmBase
from endpoint_wrapper import Endpoint, ValidationError

class MyCharm(CharmBase):
    META = {'requires': {'foo': {'interface': 'bar'}}}

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Endpoint(
            self, 'foo',
            template=template,
            # we can omit `role` and it will be guessed from META, but if we do 
            # provide it, we get nice type hints below
            role='requirer', 
            on_changed=self._on_foo_changed
        )
        
        # We are the requirer, and our template says that the local app data 
        # model for the requirer is RequirerAppModel; so we expect 
        # local_app_data to be a DataWrapper[RequirerAppModel]
        local_app_data = self.foo.relations[0].local_app_data
        # so this will work although you have to type it manually
        foo_value: int = local_app_data['foo']

        # using dot notation:
        # the IDE will autocomplete `.foo` for you, and mypy will know that foo_value_dot: int 
        foo_value_dot = local_app_data.foo
        # mypy will bash you here, because `.foo` is typed as an int, and 2.3 is a float...
        local_app_data.foo = 2.3

        # equivalent to adding an on_joined kwarg to the Endpoint:
        self.framework.observe('foo-relation-joined', self._on_foo_joined)
        
    def _on_foo_changed(self, event):
        # we can check whether:
        
        # local application data is valid:
        if self.foo.__local_app_data_valid:
            self.do_stuff() 
            
        # remote data is valid: (for all related apps, for all related units).
        if self.foo.remote_valid:
            self.do_stuff()  
            
        # all data is valid: (all remote and local data).
        if self.foo.valid:
            self.do_stuff()  
            
        # we can also idiomatically read/write data
        # this charm implements the requirer side of foo, so we have to look at RequirerAppModel.
        
        for local_app_data in self.foo.local_apps_data.values():
            local_app_data['foo'] = 42
            # equivalent to:
            # local_app_data.foo = 42  # mypy will understand this!
            
            # since we installed pydantic:
            try:
                local_app_data['foo'] = 42.3
            except ValidationError: 
              pass

    def _on_foo_joined(self, event):
        # we can 'wrap' an event's relation idiomatically:
        foo_relation = self.foo.wrap(event.relation)
        assert foo_relation.remote_app_data.valid
```

# Publishing

Don't forget to open a PR with the version bumped.
If you wish to bump the version (requires typer):
```sh 
export PYTHONPATH=$PYTHONPATH:$(pwd)
python ./scripts/bump-version.py [minor=True] [major=False]
```

To inline (embed) the stub file in the library code:
```sh 
export PYTHONPATH=$PYTHONPATH:$(pwd)
python ./scripts/inline-lib.py
```

After you've done that, you can use `sh ./scripts/publish` to publish to charmcraft.

Now you're ready to use the lib in your charms:
`charmcraft fetch-lib charms.relation_wrapper.v0.endpoint_wrapper`

