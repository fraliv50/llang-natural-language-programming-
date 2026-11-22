"""Universal porting application: source repositories -> readable llang.

The architecture is pluggable: each source language supplies an adapter that
parses with a real parser and emits llang source plus an explicit gap report.
Anything an adapter cannot translate is queued for AI cleanup rather than being
silently dropped.
"""

from .models import Adapter, ConversionResult, Gap  # noqa: F401

__all__ = ["Adapter", "ConversionResult", "Gap"]
