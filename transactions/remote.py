"""Переказ між рахунками (FR-07) та оплата послуг (FR-08)."""

from transactions.base import Receipt, Transaction


class TransferTransaction(Transaction):
    operation = "transfer"

    def execute(self, amount: int, payee: str) -> Receipt:
        self.amount = amount
        result = self._authorize(amount, payee=payee)
        self.journal.write(self.id, "transfer", result.status,
                           {"amount": amount, "payee": payee})
        return Receipt(self.id, amount, result.status,
                       "переказ виконано" if result.approved else result.reason)


class PaymentTransaction(Transaction):
    operation = "payment"

    def __init__(self, transaction_id, card, gateway, journal, services):
        super().__init__(transaction_id, card, gateway, journal)
        self.services = set(services)

    def execute(self, amount: int, service: str) -> Receipt:
        self.amount = amount
        if service not in self.services:
            self.journal.write(self.id, "payment", "DECLINED",
                               {"reason": "послуга недоступна"})
            return Receipt(self.id, amount, "DECLINED", "послуга недоступна")
        result = self._authorize(amount)
        self.journal.write(self.id, "payment", result.status,
                           {"amount": amount, "service": service})
        return Receipt(self.id, amount, result.status,
                       "оплату виконано" if result.approved else result.reason)
