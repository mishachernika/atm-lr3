"""Контролер банкомата: складання системи з модулів M1–M7 (FR-01)."""

import itertools
import json

from core.authenticator import Authenticator
from core.session import Session
from gateway.bank import BankGateway, BankSimulator
from journal.journal import Journal
from maintenance.cassette import Cassette, CashAcceptor, Dispenser
from maintenance.service import MaintenanceService
from security.security import SecurityService, TamperSensor, UpdateVerifier
from transactions.cash import DepositTransaction, WithdrawalTransaction
from transactions.limits import DailyLimit
from transactions.remote import PaymentTransaction, TransferTransaction
from ui.devices import Card, CardReader, Display, PinPad


class ATMController:
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, encoding="utf-8") as f:
            self.config = json.load(f)                 # конфігураційна мова
        cfg = self.config

        self.journal = Journal(cfg.get("journal_path", ":memory:"))         # M3
        self.bank = BankSimulator()
        self.gateway = BankGateway(self.bank, cfg["bank"]["gateway_retries"])  # M7
        self.security = SecurityService(                                    # M5
            self.gateway, self.journal, TamperSensor(),
            UpdateVerifier(cfg["update_key"], current_version="1.0"))
        self.dispenser = Dispenser([                                        # M4
            Cassette(c["id"], c["denomination"], c["count"])
            for c in cfg["cassettes"]])
        self.acceptor = CashAcceptor()
        self.maintenance = MaintenanceService(
            self.gateway, self.journal, self.dispenser,
            cfg["service_key_sha256"], cfg["low_cash_threshold"])
        self.limits = DailyLimit(cfg["bank"]["daily_withdrawal_limit"])    # M2
        self.authenticator = Authenticator(                                 # M1
            self.gateway, self.journal, cfg["bank"]["max_pin_attempts"])
        self.display = Display()                                            # M6
        self.allowed_operations = {op for op, on in cfg["operations"].items() if on}
        self._ids = itertools.count(1)

    def start_session(self, card_number: str, pin: str) -> Session:
        reader = CardReader(Card(card_number, "Клієнт"))
        session = Session(
            reader, PinPad(pin), self.display,
            self.authenticator, self.security, self.gateway,
            self._factory, self.allowed_operations)
        session.start()
        return session

    def _factory(self, kind, card):
        tx_id = f"TX-{next(self._ids):04d}"
        if kind == "withdrawal":
            return WithdrawalTransaction(tx_id, card, self.gateway,
                                        self.journal, self.dispenser, self.limits)
        if kind == "deposit":
            return DepositTransaction(tx_id, card, self.gateway,
                                      self.journal, self.acceptor)
        if kind == "transfer":
            return TransferTransaction(tx_id, card, self.gateway, self.journal)
        if kind == "payment":
            return PaymentTransaction(tx_id, card, self.gateway,
                                      self.journal, self.config["services"])
        raise ValueError("невідома операція")
