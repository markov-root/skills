"""Owned core contracts and orchestration for the doc2md package."""

from doc2md.core.application import ConvertService
from doc2md.core.models import ConversionPolicy, ConversionResult, SourceDocument

__version__ = "0.3.0"

__all__ = [
    "ConversionPolicy",
    "ConversionResult",
    "ConvertService",
    "SourceDocument",
    "__version__",
]
