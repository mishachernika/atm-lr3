"""Модульні тести прототипу (робота A11 плану ЛР2).

Запуск з каталогу atm:  python3 -m unittest discover -s tests -v
"""

import os
import tempfile
import unittest

from core.controller import ATMController
from core.session import OperationError
from gateway.bank import AuthRequest, BankSimulator
from journal.journal import Journal
from security.security import SecurityError, UpdateVerifier, parse_version
from ui.devices import AuthError

CARD, PIN = "5351****1234", "1234"


def new_session():
    atm = ATMController("config.json")
    return atm, atm.start_session(CARD, PIN)


class WithdrawalTests(unittest.TestCase):
    def setUp(self):
        self.atm, self.session = new_session()

    def test_withdrawal_ok(self):
        """FR-06: успішне зняття змінює баланс і потрапляє до журналу."""
        before = self.session.balance()
        receipt = self.session.withdraw(700)
        self.assertEqual(receipt.status, "DONE")
        self.assertEqual(self.session.balance(), before - 700)
        self.assertTrue(self.atm.journal.verify_chain())

    def test_withdrawal_insufficient_funds(self):
        """FR-12: недостатньо коштів — відмова без списання."""
        before = self.session.balance()
        receipt = self.session.withdraw(7600)
        self.assertEqual(receipt.status, "DECLINED")
        self.assertEqual(receipt.details, "недостатньо коштів")
        self.assertEqual(self.session.balance(), before)

    def test_withdrawal_dispenser_reverse(self):
        """FR-06: відмова диспенсера скасовує списання в банку."""
        before = self.session.balance()
        self.session.withdraw(50)          # 50 грн неможливо видати наявними номіналами
        self.assertEqual(self.session.balance(), before)
        self.assertEqual(self.atm.journal.events("withdrawal")[-1][2], "REVERSED")

    def test_daily_limit(self):
        """FR-06: добовий ліміт із config.json перевіряється до авторизації."""
        self.atm.limits.limit = 1000
        self.assertEqual(self.session.withdraw(700).status, "DONE")
        receipt = self.session.withdraw(500)
        self.assertEqual(receipt.status, "DECLINED")
        self.assertEqual(receipt.details, "перевищено добовий ліміт")
        self.assertEqual(self.session.balance(), 7500 - 700)

    def test_invalid_amount(self):
        """FR-12: нульова або від'ємна сума відхиляється."""
        self.assertEqual(self.session.withdraw(0).status, "DECLINED")
        self.assertEqual(self.session.withdraw(-100).status, "DECLINED")


class OperationsTests(unittest.TestCase):
    def test_transfer_payment_deposit(self):
        """FR-07–FR-09: переказ, оплата й внесення змінюють баланс."""
        atm, session = new_session()
        self.assertEqual(session.transfer(300, "5351****9999").status, "DONE")
        self.assertEqual(session.pay(150, "Мобільний зв'язок").status, "DONE")
        self.assertEqual(session.deposit(500).status, "DONE")
        self.assertEqual(session.balance(), 7500 - 300 - 150 + 500)
        self.assertEqual(atm.bank.balance("5351****9999"), 1200 + 300)

    def test_deposit_rejects_unreadable_notes(self):
        """FR-09: неприйняті купюри повертаються, зарахування немає."""
        atm, session = new_session()
        receipt = session.deposit(550)
        self.assertEqual(receipt.status, "DECLINED")
        self.assertEqual(session.balance(), 7500)

    def test_unknown_service_declined(self):
        """FR-08: послуга поза переліком із config.json відхиляється."""
        atm, session = new_session()
        self.assertEqual(session.pay(100, "Невідома").status, "DECLINED")

    def test_menu_follows_config(self):
        """FR-04: меню й дозволені операції беруться з config.json."""
        atm = ATMController("config.json")
        atm.allowed_operations.discard("transfer")
        session = atm.start_session(CARD, PIN)
        self.assertNotIn("Переказ", session.menu())
        with self.assertRaises(OperationError):
            session.transfer(100, "5351****9999")

    def test_change_pin(self):
        """FR-10: PIN змінюється лише на 4 цифри; новий PIN діє."""
        atm, session = new_session()
        with self.assertRaises(OperationError):
            session.change_pin("12")
        session.change_pin("4321")
        self.assertTrue(atm.gateway.verify_pin(CARD, "4321"))
        self.assertFalse(atm.gateway.verify_pin(CARD, PIN))

    def test_finish_resets_session(self):
        """FR-01: після завершення сесії картка вилучена, стан скинуто."""
        atm, session = new_session()
        session.finish()
        self.assertIsNone(session.card)
        self.assertEqual(atm.display.messages[-1], "Вставте картку")


class IdempotencyTests(unittest.TestCase):
    def test_repeat_request_no_double_debit(self):
        """NFR-02: повторний запит з тим самим id не списує двічі."""
        bank = BankSimulator()
        before = bank.balance(CARD)
        req = AuthRequest("TX-0001", CARD, "withdrawal", 500)
        first = bank.authorize(req)
        repeat = bank.authorize(req)
        self.assertTrue(first.approved and repeat.approved)
        self.assertEqual(bank.balance(CARD), before - 500)

    def test_lost_response_retry(self):
        """FR-12, NFR-02: відповідь банку втрачено — повтор не дублює списання."""
        atm, session = new_session()
        atm.bank.simulate_response_loss(2)
        self.assertEqual(session.withdraw(700).status, "DONE")
        self.assertEqual(session.balance(), 7500 - 700)

    def test_no_connection(self):
        """FR-12: зв'язок не відновився — зрозуміла відмова й автоматичний відкат."""
        atm, session = new_session()
        atm.bank.simulate_response_loss(10)
        receipt = session.withdraw(700)
        self.assertEqual(receipt.details, "немає зв'язку з банком")
        self.assertEqual(atm.bank.balance(CARD), 7500)   # списання скасовано
        self.assertEqual(session.transfer(100, "5351****9999").status, "DECLINED")
        self.assertEqual(atm.bank.balance("5351****9999"), 1200)


class SecurityTests(unittest.TestCase):
    def test_tamper_blocks_operations(self):
        """FR-18: втручання блокує операції, реєструється, банк сповіщений."""
        atm = ATMController("config.json")
        atm.security.sensor.tampered = True
        atm.security.check_tamper()
        with self.assertRaises(SecurityError):
            atm.start_session(CARD, PIN)
        self.assertIn("security", [e[1] for e in atm.journal.events()])
        self.assertTrue(atm.bank.security_events)

    def test_update_signature(self):
        """FR-17: встановлюється лише підписане новіше оновлення."""
        key = "bank-demo-trusted-key"
        verifier = UpdateVerifier(key, current_version="1.0")
        manifest = {"version": "1.1", "files": ["core"]}
        sig = UpdateVerifier.sign(manifest, key)
        self.assertTrue(verifier.verify({"manifest": manifest, "signature": sig}))
        self.assertFalse(verifier.verify({"manifest": manifest, "signature": "bad"}))
        self.assertFalse(verifier.verify(
            {"manifest": {"version": "0.9"}, "signature": sig}))

    def test_version_compare_numeric(self):
        """FR-17: версію 1.10 визнано новішою за 1.9."""
        self.assertGreater(parse_version("1.10"), parse_version("1.9"))
        key = "bank-demo-trusted-key"
        verifier = UpdateVerifier(key, current_version="1.9")
        manifest = {"version": "1.10"}
        self.assertTrue(verifier.verify(
            {"manifest": manifest, "signature": UpdateVerifier.sign(manifest, key)}))

    def test_install_and_rollback(self):
        """FR-17: встановлення оновлення і відновлення попередньої версії."""
        atm = ATMController("config.json")
        key = atm.config["update_key"]
        manifest = {"version": "1.1"}
        pkg = {"manifest": manifest, "signature": UpdateVerifier.sign(manifest, key)}
        self.assertTrue(atm.security.install_update(pkg))
        self.assertFalse(atm.security.install_update(
            {"manifest": {"version": "1.2"}, "signature": "bad"}))
        self.assertEqual(atm.security.rollback_update(), "1.0")
        with self.assertRaises(SecurityError):
            atm.security.rollback_update()

    def test_pin_limit_blocks_card(self):
        """FR-03: третя невдала спроба блокує картку."""
        atm = ATMController("config.json")
        with self.assertRaises(AuthError):
            atm.start_session(CARD, "0000")
        self.assertIn("BLOCKED", [e[2] for e in atm.journal.events("auth")])

    def test_pin_not_in_journal(self):
        """NFR-01: PIN-код не потрапляє до журналу."""
        atm = ATMController("config.json")
        with self.assertRaises(AuthError):
            atm.start_session(CARD, "0000")
        self.assertNotIn("0000", str(atm.journal.events()))


class JournalTests(unittest.TestCase):
    def test_tampering_detected(self):
        """NFR-06: змінений запис порушує ланцюжок SHA-256."""
        journal = Journal()
        journal.write("A", "x", "OK", {"v": 1})
        journal.write("B", "x", "OK", {"v": 2})
        self.assertTrue(journal.verify_chain())
        journal._db.execute("UPDATE events SET status='FAKE' WHERE id='A'")
        self.assertFalse(journal.verify_chain())

    def test_chain_survives_restart(self):
        """FR-14: журнал у файлі продовжує ланцюжок після перезапуску."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "journal.db")
            first = Journal(path)
            first.write("A", "x", "OK")
            first.close()
            second = Journal(path)
            second.write("B", "x", "OK")
            self.assertTrue(second.verify_chain())
            self.assertEqual(len(second.events()), 2)
            second.close()


class MaintenanceTests(unittest.TestCase):
    def test_service_mode_and_diagnostics(self):
        """FR-15/FR-16: інкасація лише в режимі SERVICE, діагностика касет."""
        atm = ATMController("config.json")
        atm.maintenance.enter_service("SECRET")
        atm.maintenance.load_cash(500, 50)
        report = atm.maintenance.run_diagnostics()
        self.assertTrue(all("count" in c for c in report["cassettes"]))
        atm.maintenance.leave_service()
        with self.assertRaises(PermissionError):
            atm.maintenance.load_cash(100, 10)

    def test_wrong_service_key(self):
        """FR-16: невірний ключ не відкриває режим SERVICE, спроба журналюється."""
        atm = ATMController("config.json")
        with self.assertRaises(PermissionError):
            atm.maintenance.enter_service("WRONG")
        self.assertEqual(atm.journal.events("maintenance")[-1][2], "DENIED")

    def test_low_cash_alert(self):
        """FR-15: пороговий залишок у касеті формує повідомлення."""
        atm = ATMController("config.json")
        atm.dispenser.cassettes[0].count = 5
        report = atm.maintenance.run_diagnostics()
        self.assertTrue(report["cassettes"][0]["low"])
        self.assertTrue(any("мало готівки" in e for e in atm.bank.security_events))


if __name__ == "__main__":
    unittest.main(verbosity=2)
