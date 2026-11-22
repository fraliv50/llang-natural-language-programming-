"""Python adapter — wraps the existing AST-to-AST converter."""

from pathlib import Path

from llang.converter import convert_source
from llang.formatter import format_source
from llang.portapp.models import ConversionResult, Gap

from . import register


class PythonAdapter:
    name = "python"
    extensions = ("py",)

    def convert(self, source: str, path: str) -> ConversionResult:
        result = convert_source(source)
        try:
            formatted = format_source(result.source)
        except Exception:
            formatted = result.source
        return ConversionResult(
            source=formatted,
            gaps=[Gap(item.node_type, item.reason, item.lineno)
                  for item in result.unsupported],
            notes=[Gap(item.node_type, item.reason, item.lineno)
                   for item in result.notes],
            stats=result.stats,
            source_language=self.name,
        )


register(PythonAdapter())
