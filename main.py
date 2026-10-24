"""Демонстраційний сценарій роботи банкомата (запуск: python3 main.py з каталогу atm)."""

from core.controller import ATMController
from security.security import UpdateVerifier


def main() -> None:
    atm = ATMController("config.json")
    session = atm.start_session("5351****1234", "1234")

    print("Меню:", session.menu())                                # FR-04
    print("Баланс:", session.balance())                           # FR-05
    print("Зняття 700:", session.withdraw(700))                   # FR-06
    print("Зняття 19000:", session.withdraw(19_000))             # FR-12: відмова
    print("Переказ 300:", session.transfer(300, "5351****9999"))  # FR-07
    print("Оплата 150:", session.pay(150, "Мобільний зв'язок"))   # FR-08
    print("Внесення 500:", session.deposit(500))                  # FR-09
    session.change_pin("4321")                                    # FR-10
    print("Баланс після операцій:", session.balance())
    session.finish()                                              # FR-01

    # обслуговування: завантаження касет (FR-16)
    atm.maintenance.enter_service("SECRET")
    atm.maintenance.load_cash(500, 50)
    print("Діагностика:", atm.maintenance.run_diagnostics())      # FR-15
    atm.maintenance.leave_service()

    # оновлення ПЗ (FR-17)
    key = atm.config["update_key"]
    manifest = {"version": "1.10", "files": ["core", "gateway"]}
    good = {"manifest": manifest, "signature": UpdateVerifier.sign(manifest, key)}
    print("Оновлення 1.10 підписане вірно:", atm.security.install_update(good))
    bad = {"manifest": {"version": "1.11"}, "signature": "00"}
    print("Оновлення з невірним підписом:", atm.security.install_update(bad))
    print("Відновлення версії:", atm.security.rollback_update())

    print("Журнал цілісний:", atm.journal.verify_chain())         # NFR-06


if __name__ == "__main__":
    main()
