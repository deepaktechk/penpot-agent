"""Image assets: URL helpers and the per-project upload cache.

Only the URL helpers are imported eagerly: the converter needs them and must not pull in
the Penpot connection.
"""
from pbridge.assets.urls import is_local, is_svg, key_for, norm_url

__all__ = ["AssetStore", "is_local", "is_svg", "key_for", "norm_url"]


def __getattr__(name: str):
    if name == "AssetStore":
        from pbridge.assets.store import AssetStore
        return AssetStore
    raise AttributeError(name)
