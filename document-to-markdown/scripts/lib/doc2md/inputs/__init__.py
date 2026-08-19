"""Safe input resolution, media detection, and archive inspection."""

from doc2md.inputs.credentials import (
    CallbackCredential,
    CredentialProvider,
    FileDescriptorCredential,
    ProtectedFileCredential,
)
from doc2md.inputs.detect import inspect_bytes
from doc2md.inputs.models import (
    ArchiveEntry,
    ArchiveInspection,
    InputErrorCode,
    InputLimits,
    InputRefusal,
    InspectedSource,
    MediaDetection,
    RetryMeaning,
    SelectorValidation,
    SubsetRequest,
)
from doc2md.inputs.resolve import (
    ReferenceKind,
    ResolvedReference,
    inspect_path,
    inspect_stream,
    resolve_reference,
)

__all__ = [
    "ArchiveEntry",
    "ArchiveInspection",
    "CallbackCredential",
    "CredentialProvider",
    "FileDescriptorCredential",
    "InputErrorCode",
    "InputLimits",
    "InputRefusal",
    "InspectedSource",
    "MediaDetection",
    "ProtectedFileCredential",
    "ReferenceKind",
    "ResolvedReference",
    "RetryMeaning",
    "SelectorValidation",
    "SubsetRequest",
    "inspect_bytes",
    "inspect_path",
    "inspect_stream",
    "resolve_reference",
]
