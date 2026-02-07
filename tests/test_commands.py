import unittest

from tests import _path  # noqa: F401
from isecnet.const import CommandCode, PGMAction, PartitionCode
from isecnet.protocol.commands.activation import ActivationCommand
from isecnet.protocol.commands.deactivation import DeactivationCommand
from isecnet.protocol.commands.pgm import PGMCommand
from isecnet.protocol.commands.siren import SirenCommand
from isecnet.protocol.commands.status import PartialStatusRequestCommand, StatusRequestCommand


class CommandTests(unittest.TestCase):
    def test_activation_build_content_partition_b(self) -> None:
        cmd = ActivationCommand.arm_partition_b("1234")
        self.assertEqual(cmd.code, CommandCode.ACTIVATION)
        self.assertEqual(cmd.partition, PartitionCode.PARTITION_B)
        self.assertEqual(cmd.build_content(), b"\x42")

    def test_deactivation_disarm_all_has_empty_content(self) -> None:
        cmd = DeactivationCommand.disarm_all("1234")
        self.assertEqual(cmd.code, CommandCode.DEACTIVATION)
        self.assertEqual(cmd.build_content(), b"")

    def test_pgm_turn_on_output_2(self) -> None:
        cmd = PGMCommand.turn_on("1234", 2)
        self.assertEqual(cmd.code, CommandCode.PGM_CONTROL)
        self.assertEqual(cmd.action, PGMAction.TURN_ON)
        self.assertEqual(cmd.output_number, 2)
        self.assertEqual(cmd.build_content(), bytes([0x4C, 0x32]))

    def test_siren_turn_off_command(self) -> None:
        cmd = SirenCommand.turn_off_siren("1234")
        self.assertEqual(cmd.code, CommandCode.SIREN_OFF)
        self.assertEqual(cmd.build_content(), b"")

    def test_status_commands_have_no_content(self) -> None:
        self.assertEqual(PartialStatusRequestCommand("1234").build_content(), b"")
        self.assertEqual(StatusRequestCommand("1234").build_content(), b"")

    def test_activation_full_build_matches_documented_bytes(self) -> None:
        cmd = ActivationCommand.arm_all("1234")
        self.assertEqual(cmd.build(), bytes.fromhex("08 E9 21 31 32 33 34 41 21 5B"))


if __name__ == "__main__":
    unittest.main()
