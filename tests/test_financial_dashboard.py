import unittest
from collections import UserDict

from mfi_tools.mfi_tools.page.tablero_financiero_eeff.balance import Balance


class Row(UserDict):
    def __init__(self, code, movement=0, balance=0, opening=0):
        super().__init__(movimiento_del_mes=movement, saldo=balance, saldo_anterior=opening)
        self.codigo_cuenta = code


class FinancialDashboardTest(unittest.TestCase):
    def test_subtotals_and_mixed_detail_do_not_duplicate(self):
        balance = Balance([Row("1", balance=100), Row("11", balance=20),
                           Row("140101", balance=30, opening=26), Row("14010101", balance=30),
                           Row("140401", balance=50, opening=54)])
        self.assertEqual(balance.position()["assets"], 100)
        self.assertEqual(balance.position()["net_portfolio"], 80)
        self.assertEqual(balance.position()["portfolio_change"], 0)

    def test_month_and_accumulated_result_include_tax_once(self):
        balance = Balance([Row("4", -25, -100), Row("4106", -20, -80),
                           Row("5", 10, 50), Row("5401", 4, 15), Row("62", 3, 7),
                           Row("6201", 3, 7), Row("63", 12, 43)])
        self.assertEqual(balance.results(0)["net"], 12)
        self.assertEqual(balance.results(1)["net"], 43)
        self.assertEqual(balance.results(0)["other_income"], 5)
        self.assertEqual(balance.results(0)["general"], 6)

    def test_only_the_requested_months_rate_can_be_used(self):
        from types import SimpleNamespace
        from mfi_tools.mfi_tools.page.tablero_financiero_eeff.report_currency import candidates, convert_amounts

        source = SimpleNamespace(name="Octubre", periodo_nombre="Octubre", moneda="NIO", rates={"USD": 36.6243})
        copy = SimpleNamespace(name="Octubre - USD", periodo_nombre="Octubre", moneda="USD", rates={})
        self.assertEqual(candidates([source, copy], "USD"), [source])
        self.assertEqual(candidates([source], "EUR"), [])
        self.assertEqual(candidates([copy], "USD"), [copy])
        self.assertEqual(convert_amounts({"net": 102270.95}, source.rates["USD"]), {"net": 2792.43})
        self.assertEqual(convert_amounts({"net": -10, "tax": 0}, 4), {"net": -2.5, "tax": 0})
