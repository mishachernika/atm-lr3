"""Безпека та перевірка оновлень (M5, FR-17, FR-18, NFR-08)."""

import hashlib
import hmac
import json


class SecurityError(Exception):
    pass


class TamperSensor:
    """Заглушка датчиків корпусу (стенд датчиків з ЛР2, п. 1.4)."""

    def __init__(self, tampered: bool = False):
        self.tampered = tampered


def parse_version(text: str) -> tuple[int, ...]:
    """'1.10' -> (1, 10): версії порівнюються за числами, а не за рядками."""
    try:
        return tuple(int(part) for part in text.split("."))
    except (ValueError, AttributeError):
        return ()


class UpdateVerifier:
    """FR-17: перевірка підпису оновлення до встановлення (схема HMAC-SHA256)."""

    def __init__(self, trusted_key: str, current_version: str):
        self.trusted_key = trusted_key.encode()
        self.current_version = current_version

    @staticmethod
    def sign(manifest: dict, key: str) -> str:
        """Підпис пакета на стороні банку (у прототипі — для стенду й тестів)."""
        canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
        return hmac.new(key.encode(), canonical.encode(),
                        hashlib.sha256).hexdigest()

    def verify(self, package: dict) -> bool:
        manifest = package.get("manifest")
        signature = package.get("signature")
        if not manifest or not signature:
            return False
        new = parse_version(manifest.get("version", ""))
        if not new or new <= parse_version(self.current_version):
            return False                      # оновлення не новіше за поточне
        expected = self.sign(manifest, self.trusted_key.decode())
        return hmac.compare_digest(expected, signature)


class SecurityService:
    def __init__(self, gateway, journal, sensor: TamperSensor,
                 verifier: UpdateVerifier):
        self.gateway = gateway
        self.journal = journal
        self.sensor = sensor
        self.verifier = verifier
        self.alarm = False
        self.installed_versions = [verifier.current_version]

    def check_tamper(self) -> None:
        """FR-18: виявлення втручання, блокування, сповіщення банку."""
        if self.sensor.tampered:
            self.alarm = True
            self.journal.write("SEC", "security", "TAMPER",
                               {"action": "операції зупинено"})
            self.gateway.notify_security("виявлено втручання в банкомат")

    def guard(self) -> None:
        """Викликається перед кожною операцією; у стані тривоги — відмова."""
        if self.alarm:
            raise SecurityError("операції заблоковано службою безпеки")

    def install_update(self, package: dict) -> bool:
        """FR-17: пакет встановлюється лише після перевірки підпису й версії."""
        if not self.verifier.verify(package):
            self.journal.write("SEC", "update", "REJECTED", {})
            return False
        version = package["manifest"]["version"]
        self.installed_versions.append(version)
        self.verifier.current_version = version
        self.journal.write("SEC", "update", "INSTALLED", {"version": version})
        return True

    def rollback_update(self) -> str:
        """FR-17: повернення до попередньої стабільної версії."""
        if len(self.installed_versions) < 2:
            raise SecurityError("немає попередньої версії для відновлення")
        self.installed_versions.pop()
        self.verifier.current_version = self.installed_versions[-1]
        self.journal.write("SEC", "update", "ROLLBACK",
                           {"version": self.verifier.current_version})
        return self.verifier.current_version
