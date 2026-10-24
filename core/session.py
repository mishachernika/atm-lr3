"""Клієнтська сесія банкомата (M1, FR-01–FR-05, FR-10)."""

from core.authenticator import Authenticator
from ui.devices import CardReader, Display, PinPad

OPERATION_TITLES = {"withdrawal": "Зняття готівки", "deposit": "Внесення готівки",
                    "transfer": "Переказ", "payment": "Оплата послуг"}


class OperationError(Exception):
    """Операція не дозволена для цього банкомата (FR-04)."""


class Session:
    def __init__(self, reader: CardReader, pin_pad: PinPad, display: Display,
                 authenticator: Authenticator, security, gateway,
                 operations_factory, allowed_operations):
        self.reader = reader
        self.pin_pad = pin_pad
        self.display = display
        self.authenticator = authenticator
        self.security = security
        self.gateway = gateway
        self.make = operations_factory
        self.allowed = set(allowed_operations)
        self.card = None
        self.attempts = 0
        self.sequence = 0

    def start(self):
        self.security.guard()
        self.card = self.reader.read()                 # FR-02
        pin = self.pin_pad.read_pin()
        while not self.authenticator.verify_pin(self.card, pin, self.attempts):
            self.attempts += 1
            self.display.show_message("Неправильний PIN")
            pin = self.pin_pad.read_pin()

    def menu(self) -> list[str]:                       # FR-04
        titles = [OPERATION_TITLES[op] for op in OPERATION_TITLES
                  if op in self.allowed]
        self.display.show_menu(titles)
        return titles

    def balance(self) -> int:                          # FR-05
        self.security.guard()
        return self.gateway.balance(self.card.number)

    def _new_transaction(self, kind: str):
        self.security.guard()
        if kind not in self.allowed:                   # FR-04: недоступні не виконуються
            raise OperationError(f"операція «{kind}» недоступна")
        self.sequence += 1
        return self.make(kind, self.card)

    def withdraw(self, amount: int):
        return self._new_transaction("withdrawal").execute(amount)    # FR-06

    def deposit(self, amount: int):
        return self._new_transaction("deposit").execute(amount)       # FR-09

    def transfer(self, amount: int, payee: str):
        tx = self._new_transaction("transfer")
        if not self.display.confirm(f"переказ {amount} грн на {payee}"):   # FR-07
            raise OperationError("клієнт не підтвердив операцію")
        return tx.execute(amount, payee)

    def pay(self, amount: int, service: str):
        tx = self._new_transaction("payment")
        if not self.display.confirm(f"оплата {amount} грн: {service}"):    # FR-08
            raise OperationError("клієнт не підтвердив операцію")
        return tx.execute(amount, service)

    def change_pin(self, new_pin: str) -> None:        # FR-10
        self.security.guard()
        if not (new_pin.isdigit() and len(new_pin) == 4):
            raise OperationError("PIN має складатися з 4 цифр")
        self.authenticator.change_pin(self.card, new_pin)

    def finish(self):                                  # FR-01: початковий стан
        self.reader.eject()
        self.card = None
        self.attempts = 0
        self.display.show_welcome()
