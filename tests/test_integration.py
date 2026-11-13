"""Пакет T3 (ЛР5): інтеграційні тести відмовостійкості IT-01…IT-08 («сірий ящик»).

Відмови вводяться засобами стенда: BankSimulator.simulate_response_loss,
TamperSensor.tampered, обнулення касет диспенсера.
"""

import json
import os
import tempfile
import unittest

from core.controller import ATMController
from security.security import SecurityError
from ui.devices import AuthError

CARD, PIN, OTHER = "5351****1234", "1234", "5351****9999"


def new_session():
    atm = ATMController("config.json")
    return atm, atm.start_session(CARD, PIN)


class FailureInjectionTests(unittest.TestCase):
    def setUp(self):
        self.atm, self.s = new_session()

    def test_it01_lost_response_single_debit(self):
        """IT-01 (FR-12, NFR-02): втрачена відповідь — повтор запиту, одне списання, DONE."""
        self.atm.bank.simulate_response_loss(1)
        r = self.s.withdraw(700)
        self.assertEqual(r.status, "DONE")
        self.assertEqual(self.s.balance(), 6800)

    def test_it02_connection_not_restored(self):
        """IT-02 (FR-12): зв'язок не відновився — DECLINED «немає зв'язку», відкат списання."""
        self.atm.bank.simulate_response_loss(3)
        r = self.s.withdraw(700)
        self.assertEqual((r.status, r.details), ("DECLINED", "немає зв'язку з банком"))
        self.assertEqual(self.s.balance(), 7500)

    def test_it03_deposit_connection_failure(self):
        """IT-03 (FR-09, FR-12): збій зв'язку при внесенні — зарахування скасовано відкатом."""
        self.atm.bank.simulate_response_loss(3)
        r = self.s.deposit(600)
        self.assertEqual(r.status, "DECLINED")
        self.assertEqual(self.s.balance(), 7500)

    def test_it04_empty_cassettes(self):
        """IT-04 (FR-06): пусті касети — REVERSED, відкат списання, запис у журналі."""
        for c in self.atm.dispenser.cassettes:
            c.count = 0
        r = self.s.withdraw(700)
        self.assertEqual(r.status, "REVERSED")
        self.assertEqual(self.s.balance(), 7500)
        self.assertEqual(self.atm.journal.events("withdrawal")[-1][2], "REVERSED")


class SecurityIntegrationTests(unittest.TestCase):
    def test_it05_tamper_during_active_session(self):
        """IT-05 (FR-18): втручання під час сесії — наступна операція SecurityError, банк сповіщено."""
        atm, s = new_session()
        atm.security.sensor.tampered = True
        with self.assertRaises(SecurityError):
            s.withdraw(100)
        self.assertTrue(atm.bank.security_events)
        self.assertEqual(atm.gateway.balance(CARD), 7500)

    def test_it06_blocked_card_in_new_session(self):
        """IT-06 (FR-03): блокування зберігається — вірний PIN у новій сесії відхиляється."""
        atm = ATMController("config.json")
        with self.assertRaises(AuthError):
            atm.start_session(CARD, "0000")
        with self.assertRaises(AuthError):
            atm.start_session(CARD, PIN)

    def test_it07_daily_limit_across_sessions(self):
        """IT-07 (FR-06): добовий ліміт діє між сесіями."""
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["bank"]["daily_withdrawal_limit"] = 2000
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            atm = ATMController(path)
            s1 = atm.start_session(CARD, PIN)
            self.assertEqual(s1.withdraw(1500).status, "DONE")
            s1.finish()
            s2 = atm.start_session(CARD, PIN)
            r = s2.withdraw(1000)
            self.assertEqual((r.status, r.details), ("DECLINED", "перевищено добовий ліміт"))

    def test_it08_end_to_end_scenario(self):
        """IT-08 (FR-01–FR-16, NFR-06): наскрізний сценарій використання й обслуговування."""
        atm, s = new_session()
        self.assertEqual(s.withdraw(700).status, "DONE")
        self.assertEqual(s.deposit(300).status, "DONE")
        self.assertEqual(s.transfer(200, OTHER).status, "DONE")
        self.assertEqual(s.pay(100, "Інтернет").status, "DONE")
        self.assertEqual(s.balance(), 7500 - 700 + 300 - 200 - 100)
        s.finish()
        atm.maintenance.enter_service("SECRET")
        atm.maintenance.load_cash(500, 50)
        self.assertEqual(atm.maintenance.run_diagnostics()["modules"], "OK")
        atm.maintenance.leave_service()
        self.assertTrue(atm.journal.verify_chain())


if __name__ == "__main__":
    unittest.main()
