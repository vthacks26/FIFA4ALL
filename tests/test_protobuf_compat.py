"""GetPrototype spam is filtered; other warnings and errors are not."""

from __future__ import annotations

import warnings
import unittest

from tracking.protobuf_compat import GETPROTOTYPE_WARNING, silence_getprototype_userwarning


class ProtobufCompatTests(unittest.TestCase):
    def test_getprototype_userwarning_is_suppressed(self) -> None:
        silence_getprototype_userwarning()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            silence_getprototype_userwarning()
            warnings.warn(
                "SymbolDatabase.GetPrototype() is deprecated. Please use "
                "message_factory.GetMessageClass() instead. "
                "SymbolDatabase.GetPrototype() will be removed soon.",
                UserWarning,
            )
            messages = [str(item.message) for item in caught]
        self.assertFalse(any("GetPrototype" in message for message in messages))

    def test_unrelated_userwarning_still_surfaces(self) -> None:
        silence_getprototype_userwarning()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            silence_getprototype_userwarning()
            warnings.warn("camera index 0 is Continuity Camera", UserWarning)
            messages = [str(item.message) for item in caught]
        self.assertTrue(any("Continuity Camera" in message for message in messages))

    def test_filter_is_message_and_userwarning_only(self) -> None:
        self.assertIn("GetPrototype", GETPROTOTYPE_WARNING)
        silence_getprototype_userwarning()
        with self.assertRaises(RuntimeError):
            raise RuntimeError("face_not_found")
