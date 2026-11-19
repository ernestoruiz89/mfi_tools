"""Choose one EEFF trial balance per month and express its amounts in the display currency."""
from decimal import Decimal
from .metrics import money


def candidates(rows, currency):
    """Prefer the original balance, then a native balance, then a convertible one."""
    available = [row for row in rows if row.moneda == currency or currency in row.rates]
    original = [row for row in available if row.name == row.periodo_nombre]
    native = [row for row in available if row.moneda == currency]
    return original or native or available


def convert_amounts(amounts, rate):
    if rate == 1:
        return amounts
    divisor = Decimal(str(rate))
    return {key: money(Decimal(str(value)) / divisor) for key, value in amounts.items()}
