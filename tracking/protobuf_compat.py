"""Face-Mesh-safe protobuf pin notes and one targeted warning filter.

``mediapipe==0.10.14`` requires ``protobuf>=4.25.3,<5``. That range is the
real compatibility constraint: protobuf 5+ removed
``SymbolDatabase.GetPrototype()``, which Face Mesh still calls.

Every 4.25.x release in that range still emits:

    UserWarning: SymbolDatabase.GetPrototype() is deprecated

from ``google/protobuf/symbol_database.py``. A pin cannot silence it without
leaving the supported range, so the launch path filters only that UserWarning.
Unrelated warnings and exceptions are left alone.
"""

from __future__ import annotations

import warnings

GETPROTOTYPE_WARNING = r"SymbolDatabase\.GetPrototype\(\) is deprecated"


def silence_getprototype_userwarning() -> None:
    """Ignore only the MediaPipe/protobuf GetPrototype UserWarning."""

    warnings.filterwarnings(
        "ignore",
        message=GETPROTOTYPE_WARNING,
        category=UserWarning,
    )
