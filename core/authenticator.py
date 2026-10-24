"""Автентифікація клієнта (M1, FR-03, FR-10)."""

from ui.devices import AuthError


class Authenticator:
    def __init__(self, gateway, journal, max_attempts: int = 3):
        self.gateway = gateway
        self.journal = journal
        self.max_attempts = max_attempts

    def verify_pin(self, card, pin: str, attempts_done: int) -> bool:
        if self.gateway.verify_pin(card.number, pin):
            return True
        if attempts_done + 1 >= self.max_attempts:      # FR-03: ліміт спроб
            self.journal.write("AUTH", "auth", "BLOCKED",
                               {"card": card.number, "attempts": attempts_done + 1})
            raise AuthError("картку заблоковано")
        return False

    def change_pin(self, card, new_pin: str) -> None:
        self.gateway.change_pin(card.number, new_pin)   # FR-10
        self.journal.write("AUTH", "pin_change", "DONE", {"card": card.number})
