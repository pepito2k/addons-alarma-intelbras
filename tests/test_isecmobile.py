import unittest

from tests import _path  # noqa: F401
from isecnet.protocol.isecmobile import ISECMobileError, ISECMobileFrame


class ISECMobileFrameTests(unittest.TestCase):
    def test_create_and_build_frame(self) -> None:
        frame = ISECMobileFrame.create("1234", 0x41)
        self.assertEqual(frame.build(), bytes.fromhex("21 31 32 33 34 41 21"))

    def test_parse_roundtrip(self) -> None:
        raw = bytes.fromhex("21 31 32 33 34 41 42 21")
        parsed = ISECMobileFrame.parse(raw)
        self.assertEqual(parsed.password, b"1234")
        self.assertEqual(parsed.command, b"\x41")
        self.assertEqual(parsed.content, b"\x42")

    def test_invalid_password_length_raises(self) -> None:
        with self.assertRaises(ISECMobileError):
            ISECMobileFrame.create("123", 0x41)

    def test_invalid_delimiter_raises(self) -> None:
        with self.assertRaises(ISECMobileError):
            ISECMobileFrame.parse(bytes.fromhex("20 31 32 33 34 41 21"))

    def test_try_parse_returns_none_for_invalid_input(self) -> None:
        self.assertIsNone(ISECMobileFrame.try_parse(b"\x21\x31\x32"))


if __name__ == "__main__":
    unittest.main()
