"""Обмін із процесинговою системою банку (M7, FR-11, NFR-02, NFR-10).

Спрощена модель протоколу авторизації з ідемпотентними запитами:
повторний запит із тим самим ідентифікатором транзакції не списує
кошти двічі (NFR-02 — цілісність операцій).
"""

from dataclasses import dataclass


class GatewayError(Exception):
    """Немає зв'язку з процесингом (тайм-аут)."""


@dataclass
class AuthRequest:
    transaction_id: str
    card_number: str
    operation: str          # withdrawal | deposit | transfer | payment
    amount: int
    payee: str = ""


@dataclass
class AuthResult:
    transaction_id: str
    approved: bool
    status: str             # DONE | DECLINED | REVERSED
    reason: str = ""


class BankSimulator:
    """Тестове середовище банку (симулятор процесингу з ЛР2, п. 1.4)."""

    def __init__(self):
        self._accounts = {
            "5351****1234": {"pin": "1234", "balance": 7500},
            "5351****9999": {"pin": "9999", "balance": 1200},
        }
        self._processed: dict[str, AuthResult] = {}
        self._source: dict[str, AuthRequest] = {}
        self.security_events: list[str] = []
        self._lost_responses = 0

    def simulate_response_loss(self, count: int) -> None:
        """Стенд: банк виконує операцію, але відповідь до банкомата не доходить."""
        self._lost_responses = count

    def verify_pin(self, card_number: str, pin: str) -> bool:
        acc = self._accounts.get(card_number)
        return acc is not None and acc["pin"] == pin

    def change_pin(self, card_number: str, new_pin: str) -> None:
        self._accounts[card_number]["pin"] = new_pin

    def balance(self, card_number: str) -> int:
        return self._accounts[card_number]["balance"]

    def authorize(self, req: AuthRequest) -> AuthResult:
        result = self._process(req)
        if self._lost_responses > 0:                     # відповідь втрачено
            self._lost_responses -= 1
            raise GatewayError("тайм-аут відповіді банку")
        return result

    def _process(self, req: AuthRequest) -> AuthResult:
        if req.transaction_id in self._processed:        # ідемпотентність
            return self._processed[req.transaction_id]
        self._source[req.transaction_id] = req
        if req.operation in ("withdrawal", "payment"):
            result = self._debit(req)
        elif req.operation == "deposit":
            self._accounts[req.card_number]["balance"] += req.amount
            result = AuthResult(req.transaction_id, True, "DONE")
        elif req.operation == "transfer":
            if req.payee not in self._accounts:
                result = AuthResult(req.transaction_id, False, "DECLINED", "одержувача не знайдено")
            else:
                result = self._debit(req)
                if result.approved:
                    self._accounts[req.payee]["balance"] += req.amount
        else:
            result = AuthResult(req.transaction_id, False, "DECLINED", "невідома операція")
        self._processed[req.transaction_id] = result
        return result

    def reverse(self, transaction_id: str) -> None:
        """Відкат операції: відмова пристрою або втрата зв'язку (FR-06, FR-12)."""
        res = self._processed.get(transaction_id)
        if res is None or not res.approved:
            return
        req = self._source[transaction_id]
        acc = self._accounts[req.card_number]
        if req.operation == "deposit":
            acc["balance"] -= req.amount
        else:
            acc["balance"] += req.amount
            if req.operation == "transfer":
                self._accounts[req.payee]["balance"] -= req.amount
        self._processed[transaction_id] = AuthResult(
            transaction_id, False, "REVERSED", "відмова пристрою")

    def log_security_event(self, text: str) -> None:
        self.security_events.append(text)

    def _debit(self, req: AuthRequest) -> AuthResult:
        acc = self._accounts[req.card_number]
        if req.amount <= 0:
            return AuthResult(req.transaction_id, False, "DECLINED", "некоректна сума")
        if acc["balance"] < req.amount:
            return AuthResult(req.transaction_id, False, "DECLINED", "недостатньо коштів")
        acc["balance"] -= req.amount
        return AuthResult(req.transaction_id, True, "DONE")


class BankGateway:
    """Канал до банку: повторний запит за тим самим ідентифікатором безпечний."""

    def __init__(self, bank: BankSimulator, retries: int = 2):
        self._bank = bank
        self.retries = retries

    def verify_pin(self, card_number: str, pin: str) -> bool:
        return self._bank.verify_pin(card_number, pin)

    def change_pin(self, card_number: str, new_pin: str) -> None:
        self._bank.change_pin(card_number, new_pin)

    def balance(self, card_number: str) -> int:
        return self._bank.balance(card_number)

    def authorize(self, req: AuthRequest) -> AuthResult:
        """Повтор з тим самим ідентифікатором безпечний (NFR-02, FR-12)."""
        for attempt in range(self.retries + 1):
            try:
                return self._bank.authorize(req)
            except GatewayError:
                if attempt == self.retries:
                    raise

    def reverse(self, transaction_id: str) -> None:
        self._bank.reverse(transaction_id)

    def notify_security(self, text: str) -> None:
        self._bank.log_security_event(text)
