# relation-wrapper

Provides high-level API to code integration interfaces with.

In charm code:

```python
from pydantic import BaseModel
from ops import CharmBase
from relation_wrapper.relation import Relations, Template, ValidationError

class RequirerAppModel(BaseModel):
    foo: int


class RequirerUnitModel(BaseModel):
    pass


class ProviderAppModel(BaseModel):
    pass


class ProviderUnitModel(BaseModel):
    bar: float


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

    
class MyCharm(CharmBase):
    META = {'requires': {'foo': {'interface': 'bar'}}

    def __init__(self, *args):
        super().__init__(*args)
        self.foo = Relations(
            self, 'foo',
            template=template,
            on_changed=self._on_foo_changed
        )
        
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
        # this charm implements the requirer side of foo, so we have to look at RequirerAppModel
        app_data = self.foo.local_app_data
        
        app_data['foo'] = 42
        
        # since we installed pydantic:
        try:
            app_data['foo'] = 42.3
        except ValidationError: 
          pass
```
