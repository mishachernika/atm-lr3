"""Технічне обслуговування та інкасація (M4, FR-15, FR-16)."""

import hashlib
import hmac


class MaintenanceService:
    def __init__(self, gateway, journal, dispenser, service_key_sha256: str,
                 low_threshold: int = 20):
        self.gateway = gateway
        self.journal = journal
        self.dispenser = dispenser
        self._key_hash = service_key_sha256      # у конфігурації лише хеш ключа
        self.low_threshold = low_threshold
        self.mode = "CLIENT"

    def enter_service(self, key: str) -> None:
        if not hmac.compare_digest(hashlib.sha256(key.encode()).hexdigest(),
                                   self._key_hash):
            self.journal.write("MAINT", "maintenance", "DENIED",
                               {"reason": "невірний ключ доступу"})
            raise PermissionError("доступ до режиму обслуговування заборонено")
        self.mode = "SERVICE"
        self.journal.write("MAINT", "maintenance", "ENTER", {"mode": "SERVICE"})

    def load_cash(self, denomination: int, notes: int) -> None:
        if self.mode != "SERVICE":
            raise PermissionError("завантаження дозволене лише в режимі SERVICE")
        self.dispenser.load(denomination, notes)
        self.journal.write("MAINT", "maintenance", "LOADED",
                           {"denomination": denomination, "notes": notes})

    def run_diagnostics(self) -> dict:
        report = {
            "cassettes": [
                {"id": c.id, "denomination": c.denomination,
                 "count": c.count, "low": c.count < self.low_threshold}   # FR-15
                for c in self.dispenser.cassettes
            ],
            "modules": "OK",
        }
        low = [c["id"] for c in report["cassettes"] if c["low"]]
        if low:                                  # FR-15: повідомлення оператору
            self.gateway.notify_security(f"мало готівки в касетах {low}")
        self.journal.write("MAINT", "diagnostics", "DONE", report)
        return report

    def leave_service(self) -> None:
        self.mode = "CLIENT"
        self.journal.write("MAINT", "maintenance", "LEAVE", {"mode": "CLIENT"})
