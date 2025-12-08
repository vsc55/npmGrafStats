#!/usr/bin/env python3
"""Dictionary subclass that tracks modifications (dirty flag)."""

from logger import get_logger

log = get_logger(__name__)

class CacheDict(dict):
    """Dictionary subclass that tracks modifications (dirty flag)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dirty = False

    @property
    def dirty(self) -> bool:
        """Indicates whether the dictionary has been modified since last reset."""
        return self._dirty

    def reset_dirty(self) -> None:
        """Reset the dirty flag to False."""
        self._dirty = False

    def mark_dirty(self) -> None:
        """Mark the dictionary as dirty."""
        self._dirty = True

    def __setitem__(self, key, value):
        """Set the item and mark the dictionary as dirty."""
        super().__setitem__(key, value)
        self.mark_dirty()

    def __delitem__(self, key):
        """Delete the item and mark the dictionary as dirty."""
        super().__delitem__(key)
        self.mark_dirty()

    def clear(self):
        """Clear all items and mark the dictionary as dirty."""
        super().clear()
        self.mark_dirty()

    def update(self, *args, **kwargs):
        """Update the dictionary with the given key/value pairs and mark as dirty."""
        super().update(*args, **kwargs)
        self.mark_dirty()

    def pop(self, *args, **kwargs):
        """Remove specified key and return the corresponding value. Mark as dirty."""
        v = super().pop(*args, **kwargs)
        self.mark_dirty()
        return v

    def popitem(self):
        """Remove and return a (key, value) pair. Mark as dirty."""
        v = super().popitem()
        self.mark_dirty()
        return v
