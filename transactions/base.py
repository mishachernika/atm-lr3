"""Базова транзакція (M2, FR-06–FR-09, FR-11–FR-13)."""

from dataclasses import dataclass

from gateway.bank import AuthRequest, AuthResult, BankGateway, GatewayError
from journal.journal import Journal
from ui.devices import Card


@dataclass
class Receipt:
    transaction_id: str
    amount: int
    status: str
    details: str = ""


class Transaction:
    """Спільна поведінка: авторизація в банку й журналювання результату."""

    operation = "base"

    def __init__(self, transaction_id: str, card: Card,
                 gateway: BankGateway, journal: Journal):
        self.id = transaction_id
        self.card = card
        self.gateway = gateway
        self.journal = journal
        self.amount = 0

    def execute(self) -> Receipt:
        raise NotImplementedError

    def _authorize(self, amount: int, payee: str = "") -> AuthResult:
        """FR-11/FR-12: запит до банку; за втрати зв'язку — зрозумілий результат."""
        try:
            return self.gateway.authorize(AuthRequest(
                transaction_id=self.id, card_number=self.card.number,
                operation=self.operation, amount=amount, payee=payee))
        except GatewayError:
            self.gateway.reverse(self.id)     # статус невідомий: безпечний відкат
            return AuthResult(self.id, False, "DECLINED", "немає зв'язку з банком")
