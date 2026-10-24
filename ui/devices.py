"""Пристрої банкомата та інтерфейс клієнта (M1/M6).

Заглушки драйверів обладнання: у тестовому стенді (ЛР2, п. 1.4)
замінюють реальні зчитувач, PIN-клавіатуру, дисплей і датчики.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    number: str
    holder: str


class CardReader:
    """Зчитувач карток (FR-02)."""

    def __init__(self, inserted: Card | None = None):
        self._inserted = inserted
        self.status = "OK"

    def read(self) -> Card:
        if self._inserted is None:
            raise CardError("картку не зчитано")
        return self._inserted

    def eject(self) -> None:
        self._inserted = None


class PinPad:
    """Захищена PIN-клавіатура (FR-03). PIN не записується у журнали (NFR-01)."""

    def __init__(self, pin: str = ""):
        self._pin = pin

    def read_pin(self) -> str:
        return self._pin


class Display:
    """Екрани та повідомлення клієнта (NFR-09)."""

    def __init__(self):
        self.messages: list[str] = []

    def show_menu(self, operations) -> None:
        self.messages.append("Меню: " + ", ".join(operations))

    def show_message(self, text: str) -> None:
        self.messages.append(text)

    def confirm(self, text: str) -> bool:
        self.messages.append("Підтвердження: " + text)
        return True

    def show_welcome(self) -> None:
        self.messages.append("Вставте картку")


class CardError(Exception):
    pass


class AuthError(Exception):
    pass
