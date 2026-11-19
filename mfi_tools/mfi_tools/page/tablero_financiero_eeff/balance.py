"""Monthly indicators from the signed amounts in a Balanza Comprobacion EEFF."""
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache

from .metrics import money

# Positive display amounts for liabilities and equity are the reverse of the
# debit-minus-credit convention used by the imported balances.
BALANCE_CODES = {
    "assets": "1", "liabilities": "-2", "equity": "-3", "cash": "11",
    "investments": "12", "net_portfolio": "14", "foreclosed": "15",
    "receivables": "16", "permanent_investments": "17", "fixed_assets": "18",
    "other_assets": "19", "financial_obligations": "-21", "institutional_financing": "-22",
    "payables": "-26", "liability_provisions": "-27", "subordinated_debt": "-28",
    "other_liabilities": "-29", "capital": "-31", "additional_capital": "-32",
    "equity_adjustments": "-34", "reserves": "-35", "retained_earnings": "-38",
    "equity_result": "-39",
}
PORTFOLIO = ("1401", "1402", "1403", "1404", "1405")
PORTFOLIO_INCOME = ("4106", "4107", "4108", "4109", "4110")
DEPRECIATION = ("540309", "540407", "540408", "540409", "540410", "540411",
                "540504", "540505", "540506")


class Balance:
    def __init__(self, rows):
        self.amounts = defaultdict(lambda: [Decimal(0)] * 3)
        for row in rows:
            code = (row.codigo_cuenta or "").strip()
            if not code.isdigit():
                raise ValueError("La balanza incluye líneas sin código contable numérico.")
            for i, field in enumerate(("movimiento_del_mes", "saldo", "saldo_anterior")):
                self.amounts[code][i] += Decimal(str(row.get(field) or 0))
        self.codes = sorted(self.amounts)
        self.cover = lru_cache(maxsize=None)(self._cover)

    def _cover(self, prefix):
        """Use an imported subtotal, or the first available level of each subtree."""
        if prefix in self.amounts:
            return [prefix]
        nodes = []
        for code in self.codes:
            if code.startswith(prefix) and (not nodes or not code.startswith(nodes[-1])):
                nodes.append(code)
        return nodes

    def value(self, field, *prefixes):
        return sum((self.amounts[c][field] for p in prefixes for c in self.cover(p)), Decimal(0))

    def results(self, field):
        revenue = -self.value(field, "4")
        tax = self.value(field, "62")
        expenses = self.value(field, "5") + tax
        portfolio_income = -self.value(field, *PORTFOLIO_INCOME)
        financial = self.value(field, "51", "55")
        personnel = self.value(field, "5401")
        provisions = self.value(field, "52")
        depreciation = self.value(field, *DEPRECIATION)
        net = revenue - expenses
        amounts = dict(revenue=revenue, expenses=expenses, portfolio_income=portfolio_income,
                       other_income=revenue-portfolio_income, financial_expenses=financial,
                       personnel=personnel, provisions=provisions, depreciation=depreciation, tax=tax,
                       general=expenses-tax-financial-personnel-provisions-depreciation,
                       net=net, operating=net+tax+provisions+depreciation)
        return {key: money(value) for key, value in amounts.items()}

    def position(self):
        amounts = {key: money(self.value(1, code.lstrip("-")) * (-1 if code.startswith("-") else 1))
                   for key, code in BALANCE_CODES.items()}
        amounts["gross_portfolio"] = money(self.value(1, *PORTFOLIO))
        amounts["portfolio_change"] = money(self.value(1, *PORTFOLIO)-self.value(2, *PORTFOLIO))
        return amounts
