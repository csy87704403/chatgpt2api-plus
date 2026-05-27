from __future__ import annotations

def create_storage_backend(*args, **kwargs):
    from services.storage.factory import create_storage_backend as factory

    return factory(*args, **kwargs)


__all__ = ["create_storage_backend"]
