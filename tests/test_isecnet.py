import unittest

from tests import _path  # noqa: F401
from isecnet.protocol.isecnet import ISECNetError, ISECNetFrame, ISECNetFrameReader


class ISECNetFrameTests(unittest.TestCase):
    def test_build_matches_documented_example(self) -> None:
        mobile_content = bytes.fromhex("21 31 32 33 34 41 21")
        frame = ISECNetFrame.create_mobile_frame(mobile_content)
        self.assertEqual(frame.build(), bytes.fromhex("08 E9 21 31 32 33 34 41 21 5B"))

    def test_parse_roundtrip(self) -> None:
        built = ISECNetFrame(command=0xE9, content=b"\xAA\xBB").build()
        parsed = ISECNetFrame.parse(built)
        self.assertEqual(parsed.command, 0xE9)
        self.assertEqual(parsed.content, b"\xAA\xBB")

    def test_parse_invalid_checksum_raises(self) -> None:
        with self.assertRaises(ISECNetError):
            ISECNetFrame.parse(bytes.fromhex("08 E9 21 31 32 33 34 41 21 00"))


class ISECNetFrameReaderTests(unittest.TestCase):
    def test_reader_handles_heartbeat_and_frame(self) -> None:
        reader = ISECNetFrameReader()
        payload = ISECNetFrame(command=0xE9, content=b"\xFE").build()
        frames = reader.feed(b"\xF7" + payload)

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].command, 0xF7)
        self.assertEqual(frames[1].command, 0xE9)
        self.assertEqual(frames[1].content, b"\xFE")

    def test_reader_handles_partial_feeds(self) -> None:
        reader = ISECNetFrameReader()
        payload = ISECNetFrame(command=0xE9, content=b"\xFE").build()

        first_half = payload[:2]
        second_half = payload[2:]

        self.assertEqual(reader.feed(first_half), [])
        frames = reader.feed(second_half)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].content, b"\xFE")
        self.assertEqual(reader.pending_bytes, 0)


if __name__ == "__main__":
    unittest.main()
