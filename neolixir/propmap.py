from __future__ import absolute_import
from itertools import chain
from . import overrides
from py2neo import neo4j
from .dummy import DummyEntity
from .metadata import metadata as m
from .properties import Property

class PropMap(dict):

    def get_key(self, value):
        if not isinstance(value, (DummyEntity, neo4j.Node, neo4j.Relationship)):
            if getattr(value, '_entity', None) is None:
                return value
            else:
                value = value._entity
        return "{0}:{1}".format(value.__class__.__name__, value.id)

    def get_properties(self, value):
        key = self.get_key(value)
        if isinstance(value, (DummyEntity, neo4j.Node, neo4j.Relationship)):
            try:
                return self[key]
            except KeyError:
                self[key] = PropDict(value.properties)
                return self[key]
        else:
            try:
                return self[value]
            except KeyError:
                if value.is_phantom():
                    return self.setdefault(value, PropDict())
                else:
                    try:
                        return self[key]
                    except KeyError:
                        self[key] = PropDict(value._entity.properties)
                        return self[key]

    def remove(self, value):
        key = self.get_key(value)
        self.pop(key, None)
        self.pop(value, None)

class PropDict(dict):

    def __init__(self, data=None):
        super(PropDict, self).__init__()
        self.owner = None
        if isinstance(data, dict):
            super(PropDict, self).update(data)
        self._dirty = False

    def is_dirty(self):
        return self._dirty

    def set_dirty(self, dirty=True):
        self._dirty = dirty

    @property
    def cache(self):
        try:
            return self.owner._entity.properties
        except:
            return {}

    def reset(self, clear=True):
        """
        Reset properties to py2neo-cached values
        """
        if clear:
            super(PropDict, self).clear()
            dirty = False
        else:
            dirty = self.is_dirty()

        super(PropDict, self).update(self.cache)

        self.set_dirty(dirty)

    def reload(self, clear=True):
        """
        Reload properties from server
        """
        if clear:
            super(PropDict, self).clear()
            dirty = False
        else:
            dirty = self.is_dirty()

        if self.owner and not self.owner.is_phantom():
            if not isinstance(self.owner._entity, DummyEntity):
                self.owner._entity.properties.pull()
            super(PropDict, self).update(self.owner._entity.properties)

        self.set_dirty(dirty)

    def sanitize(self):
        super(PropDict, self).__setitem__('__class__', self.owner.__class__.__name__)
        for name, descriptor in self.owner.descriptors.iteritems():
            if isinstance(descriptor, Property) and self.get(name) is None:
                default = descriptor.get_default(self.owner)
                if default is not None:
                    descriptor.__set__(self.owner, default)

    def save(self):
        self.sanitize()
        self.owner._entity.set_properties(self)
        self.set_dirty(False)

    def __setitem__(self, key, value):
        current = self.get(key)
        if key not in self or value != current:
            super(PropDict, self).__setitem__(key, value)
            if not self.owner.is_phantom() and self.owner.has_observer('change', key):
                self.owner.fire_event('change', key, current, self.get(key))
            self.set_dirty()

    def setdefault(self, key, default=None):
        if key in self:
            return self[key]
        else:
            value = super(PropDict, self).setdefault(key, default)
            if not self.owner.is_phantom() and self.owner.has_observer('change', key):
                self.owner.fire_event('change', key, None, value)
            self.set_dirty()
            return value

    def update(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError('update expected at most 1 arguments')
        elif len(args) == 1:
            iterator = chain(args[0].iteritems() if isinstance(args[0], dict) else args[0],
                             kwargs.iteritems())
        else:
            iterator = kwargs.iteritems()
        for key, value in iterator:
            self[key] = value
