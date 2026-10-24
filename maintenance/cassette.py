"""Касети з купюрами, диспенсер і приймач готівки (M4, FR-06, FR-09, FR-15)."""


class DispenserError(Exception):
    pass


class Cassette:
    def __init__(self, cassette_id: int, denomination: int, count: int):
        self.id = cassette_id
        self.denomination = denomination
        self.count = count

    def take(self, notes: int) -> None:
        if notes > self.count:
            raise DispenserError(f"недостатньо купюр у касеті {self.id}")
        self.count -= notes

    def put(self, notes: int) -> None:
        self.count += notes


class Dispenser:
    """Видача готівки касетами за спаданням номіналу (жадібний алгоритм)."""

    def __init__(self, cassettes: list[Cassette]):
        self.cassettes = sorted(cassettes, key=lambda c: -c.denomination)

    def dispense(self, amount: int) -> list[tuple[int, int]]:
        rest = amount
        plan: list[tuple[int, int]] = []
        for c in self.cassettes:
            notes = min(rest // c.denomination, c.count)
            if notes:
                plan.append((c.denomination, notes))
                rest -= notes * c.denomination
        if rest != 0:
            raise DispenserError("суму неможливо видати наявними номіналами")
        for denomination, notes in plan:
            self._by_denomination(denomination).take(notes)
        return plan

    def load(self, denomination: int, notes: int) -> None:
        self._by_denomination(denomination).put(notes)

    def _by_denomination(self, denomination: int) -> Cassette:
        for c in self.cassettes:
            if c.denomination == denomination:
                return c
        raise DispenserError("касету не знайдено")


class CashAcceptor:
    """Приймач купюр: у стенді приймає будь-яку кратну 100 суму (FR-09)."""

    def accept(self, amount: int) -> int:
        if amount % 100 != 0:
            return amount - amount % 100     # неприйнятий залишок повертається
        return amount
