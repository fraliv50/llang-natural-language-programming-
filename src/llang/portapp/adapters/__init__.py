"""Source-language adapters.

Each adapter exposes `name`, `extensions` and `convert(source, path)` and
returns a `ConversionResult` with explicit gaps.
"""

ADAPTERS = []


def register(adapter):
    ADAPTERS.append(adapter)
    return adapter


def adapter_for(path: str):
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    for adapter in ADAPTERS:
        if suffix in adapter.extensions:
            return adapter
    return None


from .python import PythonAdapter  # noqa: E402,F401  (registers itself)
from .c import CAdapter  # noqa: E402,F401  (registers itself)
from .javascript import JavaScriptAdapter  # noqa: E402,F401  (registers itself)
