"""graderproof: mutation and metamorphic testing for agent-benchmark graders.

graderproof measures a grader's false-accept rate (validated spec-violating
variants of the reference solution that it passes) and false-reject rate
(validated spec-preserving variants that it fails), with evidence for every flag.
"""

from graderproof.core import (
    Determinism,
    GraderRun,
    Task,
    Validation,
    ValidationStatus,
    Variant,
    VariantKind,
    canonical_json,
    determinism,
    sha256_text,
)

__version__ = "0.0.1"

__all__ = [
    "Determinism",
    "GraderRun",
    "Task",
    "Validation",
    "ValidationStatus",
    "Variant",
    "VariantKind",
    "__version__",
    "canonical_json",
    "determinism",
    "sha256_text",
]
