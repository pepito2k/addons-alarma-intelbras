import unittest

from tests import _path  # noqa: F401
from isecnet.const import ResponseCode
from isecnet.protocol.commands.connection import ConnectionChannel, ConnectionInfo
from isecnet.protocol.commands.status import (
    CentralStatus,
    PartialCentralStatus,
    PartitionStatus,
    ZoneStatus,
)
from isecnet.protocol.isecnet import ISECNetFrame
from isecnet.protocol.responses import Response, ResponseParser, ResponseType


class ResponseTests(unittest.TestCase):
    def test_parse_ack_frame(self) -> None:
        response = Response.parse(bytes.fromhex("02 E9 FE EA"))
        self.assertEqual(response.response_type, ResponseType.ACK)
        self.assertTrue(response.is_success)
        self.assertEqual(response.code, ResponseCode.ACK)

    def test_parse_nack_frame(self) -> None:
        response = Response.parse(bytes.fromhex("02 E9 E1 F5"))
        self.assertEqual(response.response_type, ResponseType.NACK)
        self.assertTrue(response.is_error)
        self.assertEqual(response.error_code, ResponseCode.NACK_WRONG_PASSWORD)

    def test_parse_data_response(self) -> None:
        frame_bytes = ISECNetFrame(command=0xE9, content=bytes(range(43))).build()
        response = Response.parse(frame_bytes)
        self.assertEqual(response.response_type, ResponseType.DATA)
        self.assertTrue(response.is_success)
        self.assertEqual(len(response.data), 43)

    def test_try_parse_returns_none_for_invalid_packet(self) -> None:
        self.assertIsNone(Response.try_parse(b"\x01\x02"))

    def test_response_parser_helpers(self) -> None:
        ack_frame = ISECNetFrame(command=0xE9, content=bytes([ResponseCode.ACK]))
        nack_frame = ISECNetFrame(command=0xE9, content=bytes([ResponseCode.NACK_INVALID_PACKET]))

        self.assertTrue(ResponseParser.is_ack_frame(ack_frame))
        self.assertTrue(ResponseParser.is_nack_frame(nack_frame))
        self.assertIn("inválido", ResponseParser.get_nack_reason(nack_frame).lower())


class StatusTests(unittest.TestCase):
    def test_zone_bitmask_parser(self) -> None:
        zones = ZoneStatus._parse_bitmask(bytes([0b00000101]), start_zone=1)
        self.assertEqual(zones, {1, 3})

    def test_partition_status_properties(self) -> None:
        partitions = PartitionStatus(partition_a_armed=True, partition_b_armed=False)
        self.assertTrue(partitions.any_armed)
        self.assertFalse(partitions.all_armed)

    def test_central_status_try_parse_invalid_length(self) -> None:
        self.assertIsNone(CentralStatus.try_parse(b"\x00" * 53))

    def test_partial_status_invalid_datetime_is_none(self) -> None:
        data = bytearray(43)
        data[26] = 13  # month out of range
        parsed = PartialCentralStatus.parse(data)
        self.assertIsNone(parsed.central_datetime)


class ConnectionInfoTests(unittest.TestCase):
    def test_connection_info_parse(self) -> None:
        info = ConnectionInfo.parse(bytes.fromhex("45 12 34 30 00 01"))
        self.assertEqual(info.channel, ConnectionChannel.ETHERNET)
        self.assertEqual(info.account, "1234")
        self.assertEqual(info.mac_suffix, "30:00:01")

    def test_unknown_channel_falls_back_to_ethernet(self) -> None:
        info = ConnectionInfo.parse(bytes.fromhex("99 12 34 30 00 01"))
        self.assertEqual(info.channel, ConnectionChannel.ETHERNET)


if __name__ == "__main__":
    unittest.main()
