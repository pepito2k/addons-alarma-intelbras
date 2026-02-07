import unittest

from tests import _path  # noqa: F401
from isecnet.protocol.checksum import CRC16, Checksum


class ChecksumTests(unittest.TestCase):
    def test_checksum_example_from_docs(self) -> None:
        data = bytes([0x08, 0xE9, 0x21, 0x31, 0x32, 0x33, 0x34, 0x41, 0x21])
        self.assertEqual(Checksum.calculate(data), 0x5B)

    def test_append_and_validate_packet(self) -> None:
        packet = Checksum.append(b"\x01\x02\x03")
        self.assertTrue(Checksum.validate_packet(packet))
        self.assertFalse(Checksum.validate_packet(packet[:-1] + b"\x00"))

    def test_validate_packet_requires_payload_and_checksum(self) -> None:
        self.assertFalse(Checksum.validate_packet(b""))
        self.assertFalse(Checksum.validate_packet(b"\x01"))


class CRC16Tests(unittest.TestCase):
    def test_crc16_known_vector(self) -> None:
        # Fixed expected value helps catch regressions.
        self.assertEqual(CRC16.calculate(b"\x01\x02\x03"), 0x0C1E)
        self.assertEqual(CRC16.calculate_bytes(b"\x01\x02\x03"), b"\x0c\x1e")

    def test_crc16_append_and_validate(self) -> None:
        packet = CRC16.append(b"\x12\x34")
        self.assertTrue(CRC16.validate_packet(packet))
        self.assertFalse(CRC16.validate_packet(packet[:-1] + b"\x00"))


if __name__ == "__main__":
    unittest.main()
