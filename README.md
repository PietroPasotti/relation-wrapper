# relation-wrapper

Provides high-level API to code relation interfaces with.

In charm code:

```python
from pydantic import BaseModel
class RequirerAppModel(BaseModel):
    foo: int

class ProviderUnitModel(BaseModel):
    bar: float
```
Alternatively, you can use dataclasses and things will work just the same 
(but validation will be stricter, if enabled).


```python
from dataclasses import dataclass

@dataclass
class RequirerAppModel:
    foo: int
    
@dataclass
class ProviderUnitModel:
    bar: float
```

Now let's define a template: that is, a spec of the shape of all 
databags involved in the relation.

```python
from endpoint_wrapper import Template, DataBagModel

template = Template(
    requirer=DataBagModel(
        app=RequirerAppModel,
    ),
    provider=DataBagModel(
        unit=ProviderUnitModel
    )
)
```

Now we can use the template in combination with the EndpointWrapper:

```python
from ops import CharmBase
from endpoint_wrapper import EndpointWrapper, ValidationError

class MyCharm(CharmBase):
    META = {'requires': {'foo': {'interface': 'bar'}}}

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = EndpointWrapper(
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
        # the IDE will autocomplete `.foo` for you:
        foo_value = local_app_data.foo
        # mypy will bash you here, because `.foo` is typed as an int, and 2.3 is a float...
        local_app_data.foo = 2.3

        # equivalent to adding an on_joined kwarg to the EndpointWrapper:
        self.framework.observe('foo-relation-joined', self._on_foo_joined)
        
    def _on_foo_changed(self, event):
        # we can check whether:
        
        # local application data is valid:
        if self.foo.local_app_data_valid:
            self.do_stuff() 
            
        # remote data is valid: (for all related apps, for all related units).
        if self.foo.remote_valid:
            self.do_stuff()  
            
        # all data is valid: (all remote and local data).
        if self.foo.valid:
            self.do_stuff()  
            
        # we can also idiomatically read/write data
        # this charm implements the requirer side of foo, so we have to look at RequirerAppModel.
        
        # 
        
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

Note that the whole templating thing is fully optional.
EndpointWrapper is useful also without any templating:

```python
from ops import CharmBase
from endpoint_wrapper import EndpointWrapper
from dataclasses import dataclass

@dataclass
class Rambo:
    film: int
    
@dataclass
class Arnold:
    terminator: True
    
class MyCharm(CharmBase):
    META = {'requires': {'foo': {'interface': 'bar'}}}

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = EndpointWrapper(
            self, 'foo',
            on_changed=self._on_foo_changed
        )
        
    def _on_foo_changed(self, event):
        foo = self.foo.wrap(event.relation)
        foo.local_app_data.cheese = 'cake'
        foo.local_app_data.rambo = Rambo(film=2)
        assert foo.remote_app_data['arnold']['terminator']
```