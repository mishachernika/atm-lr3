"""Добовий ліміт зняття готівки (M2, FR-06)."""


class DailyLimit:
    """Облік знятого за добу по картках; перевірка виконується до авторизації."""

    def __init__(self, limit: int):
        self.limit = limit
        self._withdrawn: dict[str, int] = {}

    def withdrawn(self, card_number: str) -> int:
        return self._withdrawn.get(card_number, 0)

    def allows(self, card_number: str, amount: int) -> bool:
        return self.withdrawn(card_number) + amount <= self.limit

    def register(self, card_number: str, amount: int) -> None:
        self._withdrawn[card_number] = self.withdrawn(card_number) + amount
