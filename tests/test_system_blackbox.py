"""Пакет T2 (ЛР5): системні функціональні тести «чорного ящика» ST-01…ST-21.

Тести звертаються лише до публічного інтерфейсу сесії:
start_session(), menu(), balance(), операції та finish().
Класи еквівалентності й граничні значення — за вимогами FR-03, FR-04, FR-06–FR-10, FR-12.
"""

import json
import os
import tempfile
import unittest

from core.controller import ATMController
from core.session import OperationError
from ui.devices import AuthError

CARD, PIN, OTHER = "5351****1234", "1234", "5351****9999"


def new_session(config_path="config.json"):
    atm = ATMController(config_path)
    return atm, atm.start_session(CARD, PIN)


class MenuAndSessionTests(unittest.TestCase):
    def test_st01_menu_matches_config(self):
        """ST-01 (FR-04): меню містить рівно 4 операції з config.json."""
        _, s = new_session()
        self.assertEqual(len(s.menu()), 4)

    def test_st02_disabled_operation_hidden_and_refused(self):
        """ST-02 (FR-04): вимкнена операція відсутня в меню, її виклик — OperationError."""
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["operations"]["deposit"] = False
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            _, s = new_session(path)
            self.assertNotIn("Внесення готівки", s.menu())
            with self.assertRaises(OperationError):
                s.deposit(100)

    def test_st03_finish_resets_session(self):
        """ST-03 (FR-01): після finish() картку вилучено, спроби скинуто, екран «Вставте картку»."""
        atm, s = new_session()
        s.withdraw(700)
        s.finish()
        self.assertIsNone(s.card)
        self.assertEqual(s.attempts, 0)
        self.assertEqual(atm.display.messages[-1], "Вставте картку")


class WithdrawalEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.atm, self.s = new_session()

    def test_st04_negative_amount(self):
        """ST-04 (FR-12): від'ємна сума — відмова без списання."""
        r = self.s.withdraw(-100)
        self.assertEqual((r.status, r.details), ("DECLINED", "некоректна сума"))
        self.assertEqual(self.s.balance(), 7500)

    def test_st05_zero_amount(self):
        """ST-05 (FR-12): нульова сума — відмова."""
        r = self.s.withdraw(0)
        self.assertEqual((r.status, r.details), ("DECLINED", "некоректна сума"))

    def test_st06_valid_amount(self):
        """ST-06 (FR-06): коректна сума — DONE, списання, запис у журналі."""
        r = self.s.withdraw(700)
        self.assertEqual(r.status, "DONE")
        self.assertEqual(self.s.balance(), 6800)
        self.assertEqual(self.atm.journal.events("withdrawal")[-1][2], "DONE")

    def test_st07_boundary_equal_to_balance(self):
        """ST-07 (FR-06): гранична сума, що дорівнює залишку."""
        r = self.s.withdraw(7500)
        self.assertEqual(r.status, "DONE")
        self.assertEqual(self.s.balance(), 0)

    def test_st08_boundary_balance_plus_one(self):
        """ST-08 (FR-12): залишок + 1 — відмова «недостатньо коштів»."""
        r = self.s.withdraw(7501)
        self.assertEqual((r.status, r.details), ("DECLINED", "недостатньо коштів"))
        self.assertEqual(self.s.balance(), 7500)

    def test_st09_amount_not_multiple_of_denominations(self):
        """ST-09 (FR-06, FR-12): сума некратна номіналам — REVERSED і відкат списання."""
        r = self.s.withdraw(750)
        self.assertEqual(r.status, "REVERSED")
        self.assertEqual(self.s.balance(), 7500)
        self.assertEqual(self.atm.journal.events("withdrawal")[-1][2], "REVERSED")


class DepositEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.atm, self.s = new_session()

    def test_st10_negative_amount(self):
        """ST-10 (FR-12): від'ємне внесення відхиляється, баланс не змінюється."""
        r = self.s.deposit(-100)
        self.assertEqual(r.status, "DECLINED")
        self.assertEqual(self.s.balance(), 7500)

    def test_st11_zero_amount(self):
        """ST-11 (FR-12): нульове внесення — DECLINED «некоректна сума»."""
        r = self.s.deposit(0)
        self.assertEqual((r.status, r.details), ("DECLINED", "некоректна сума"))

    def test_st12_valid_amount(self):
        """ST-12 (FR-09): коректне внесення зараховується."""
        r = self.s.deposit(600)
        self.assertEqual(r.status, "DONE")
        self.assertEqual(self.s.balance(), 8100)

    def test_st13_amount_not_multiple_of_100(self):
        """ST-13 (FR-09): некратна 100 сума — купюри повернено, без зарахування."""
        r = self.s.deposit(550)
        self.assertEqual(r.status, "DECLINED")
        self.assertEqual(self.s.balance(), 7500)


class TransferPaymentTests(unittest.TestCase):
    def setUp(self):
        self.atm, self.s = new_session()

    def test_st14_transfer_known_payee(self):
        """ST-14 (FR-07): переказ відомому одержувачу змінює обидва рахунки."""
        r = self.s.transfer(300, OTHER)
        self.assertEqual(r.status, "DONE")
        self.assertEqual(self.s.balance(), 7200)
        self.assertEqual(self.atm.gateway.balance(OTHER), 1500)

    def test_st15_transfer_unknown_payee(self):
        """ST-15 (FR-07): невідомий одержувач — відмова."""
        r = self.s.transfer(300, "0000****0000")
        self.assertEqual((r.status, r.details), ("DECLINED", "одержувача не знайдено"))
        self.assertEqual(self.s.balance(), 7500)

    def test_st16_transfer_negative_amount(self):
        """ST-16 (FR-12): від'ємний переказ відхиляється без списання."""
        r = self.s.transfer(-200, OTHER)
        self.assertEqual(r.status, "DECLINED")
        self.assertEqual(self.s.balance(), 7500)
        self.assertEqual(self.atm.gateway.balance(OTHER), 1200)

    def test_st17_payment_known_service(self):
        """ST-17 (FR-08): оплата послуги зі списку."""
        r = self.s.pay(150, "Мобільний зв'язок")
        self.assertEqual(r.status, "DONE")
        self.assertEqual(self.s.balance(), 7350)

    def test_st18_payment_unknown_service(self):
        """ST-18 (FR-08): послуга поза списком — «послуга недоступна»."""
        r = self.s.pay(150, "Телебачення")
        self.assertEqual((r.status, r.details), ("DECLINED", "послуга недоступна"))
        self.assertEqual(self.s.balance(), 7500)


class AuthenticationTests(unittest.TestCase):
    def test_st19_three_wrong_pins(self):
        """ST-19 (FR-03): три невдалі спроби PIN — AuthError."""
        atm = ATMController("config.json")
        with self.assertRaises(AuthError):
            atm.start_session(CARD, "0000")

    def test_st20_new_pin_rules(self):
        """ST-20 (FR-10): неканонічні PIN відхилено, «4321» прийнято."""
        _, s = new_session()
        for bad in ("12ab", "12345"):
            with self.assertRaises(OperationError):
                s.change_pin(bad)
        s.change_pin("4321")

    def test_st21_new_pin_works(self):
        """ST-21 (FR-10): після зміни діє новий PIN, старий — ні."""
        atm, s = new_session()
        s.change_pin("4321")
        s.finish()
        atm.start_session(CARD, "4321")
        with self.assertRaises(AuthError):
            atm.start_session(CARD, "1234")


if __name__ == "__main__":
    unittest.main()
