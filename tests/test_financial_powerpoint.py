"""PowerPoint subprocess failures should become actionable Frappe errors."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from mfi_tools.mfi_tools.page.tablero_financiero_eeff import financial_report


class FinancialPowerpointTest(unittest.TestCase):
    def test_missing_node_package_is_reported_without_raw_subprocess_error(self):
        failed = subprocess.CompletedProcess(
            args=["node"], returncode=1,
            stderr="Error: Cannot find module 'pptxgenjs'\ncode: 'MODULE_NOT_FOUND'",
            stdout="",
        )
        with patch.object(financial_report.subprocess, "run", return_value=failed), \
                patch.object(financial_report.frappe, "logger") as logger, \
                patch.object(financial_report, "_", side_effect=lambda message: message), \
                patch.object(financial_report.frappe, "throw", side_effect=RuntimeError("frappe.throw")) as throw:
            with self.assertRaises(RuntimeError):
                financial_report._run_powerpoint_generator(Path("script"), Path("source"), Path("target"))

        self.assertIn("Faltan componentes", throw.call_args.args[0])
        logger.return_value.error.assert_called_once()

    def test_success_without_output_is_reported(self):
        completed = subprocess.CompletedProcess(args=["node"], returncode=0, stderr="", stdout="")
        with patch.object(financial_report.subprocess, "run", return_value=completed), \
                patch.object(financial_report.frappe, "logger") as logger, \
                patch.object(financial_report, "_", side_effect=lambda message: message), \
                patch.object(financial_report.frappe, "throw", side_effect=RuntimeError("frappe.throw")) as throw:
            with self.assertRaises(RuntimeError):
                financial_report._run_powerpoint_generator(Path("script"), Path("source"), Path("missing-target"))

        self.assertIn("No se pudo generar", throw.call_args.args[0])
        logger.return_value.error.assert_called_once()
