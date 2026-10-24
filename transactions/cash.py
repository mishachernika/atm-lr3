"""Зняття готівки (FR-06) та внесення готівки (FR-09) — робота з касетами."""

from maintenance.cassette import DispenserError
from transactions.base import Receipt, Transaction


class WithdrawalTransaction(Transaction):
    operation = "withdrawal"

    def __init__(self, transaction_id, card, gateway, journal, dispenser, limits):
        super().__init__(transaction_id, card, gateway, journal)
        self.dispenser = dispenser
        self.limits = limits

    def _decline(self, amount: int, reason: str, status: str = "DECLINED") -> Receipt:
        self.journal.write(self.id, "withdrawal", status,
                           {"reason": reason, "amount": amount})
        return Receipt(self.id, amount, status, reason)

    def execute(self, amount: int) -> Receipt:
        self.amount = amount
        if amount <= 0:
            return self._decline(amount, "некоректна сума")
        if not self.limits.allows(self.card.number, amount):      # FR-06: ліміти
            return self._decline(amount, "перевищено добовий ліміт")
        if amount > self.gateway.balance(self.card.number):
            return self._decline(amount, "недостатньо коштів")
        result = self._authorize(amount)
        if not result.approved:
            return self._decline(amount, result.reason, result.status)
        try:
            self.dispenser.dispense(amount)
        except DispenserError:
            self.gateway.reverse(self.id)                         # FR-06: відмова пристрою
            return self._decline(amount, "відмова диспенсера", "REVERSED")
        self.limits.register(self.card.number, amount)
        self.journal.write(self.id, "withdrawal", "DONE", {"amount": amount})
        return Receipt(self.id, amount, "DONE", "видано готівку")


class DepositTransaction(Transaction):
    operation = "deposit"

    def __init__(self, transaction_id, card, gateway, journal, acceptor):
        super().__init__(transaction_id, card, gateway, journal)
        self.acceptor = acceptor

    def execute(self, amount: int) -> Receipt:
        self.amount = amount
        accepted = self.acceptor.accept(amount)
        if accepted != amount:
            self.journal.write(self.id, "deposit", "DECLINED",
                               {"returned": amount - accepted})
            return Receipt(self.id, amount, "DECLINED", "неприйняті купюри повернено")
        result = self._authorize(amount)
        self.journal.write(self.id, "deposit", result.status, {"amount": amount})
        details = "зараховано на рахунок" if result.approved else result.reason
        return Receipt(self.id, amount, result.status, details)
