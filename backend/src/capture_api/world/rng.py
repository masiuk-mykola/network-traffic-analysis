import hashlib
import random
from collections.abc import MutableSequence, Sequence

_TWO_53 = float(1 << 53)


def stream_digest(seed: str, *keys: object) -> bytes:
    material = f"{seed}|{'|'.join(map(str, keys))}".encode()
    return hashlib.blake2b(material, digest_size=16).digest()


def stable_int(seed: str, *keys: object, bits: int = 64) -> int:
    if not 1 <= bits <= 128:
        raise ValueError("bits must be in 1..128")
    return int.from_bytes(stream_digest(seed, *keys), "big") >> (128 - bits)


class Stream:
    __slots__ = ("_keys", "_rng", "_seed")

    def __init__(self, seed: str, *keys: object) -> None:
        self._seed = seed
        self._keys: tuple[object, ...] = keys
        self._rng = random.Random(int.from_bytes(stream_digest(seed, *keys), "big"))

    @property
    def seed(self) -> str:
        return self._seed

    @property
    def keys(self) -> tuple[object, ...]:
        return self._keys

    def fork(self, *keys: object) -> "Stream":
        return Stream(self._seed, *self._keys, *keys)

    def bits(self, k: int) -> int:
        if k < 0:
            raise ValueError("k must be >= 0")
        return self._rng.getrandbits(k) if k else 0

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError("n must be > 0")
        k = n.bit_length()
        r = self._rng.getrandbits(k)
        while r >= n:
            r = self._rng.getrandbits(k)
        return r

    def randint(self, a: int, b: int) -> int:
        if b < a:
            raise ValueError("empty range")
        return a + self.randbelow(b - a + 1)

    def random(self) -> float:
        return self._rng.getrandbits(53) / _TWO_53

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def chance(self, p: float) -> bool:
        return self.random() < p

    def jitter(self, value: float, fraction: float) -> float:
        return value * (1.0 + self.uniform(-fraction, fraction))

    def approx_normal(self, mu: float, sigma: float) -> float:
        return mu + sigma * (sum(self.random() for _ in range(12)) - 6.0)

    def choice[T](self, items: Sequence[T]) -> T:
        if not items:
            raise IndexError("choice from an empty sequence")
        return items[self.randbelow(len(items))]

    def weighted_choice[T](self, items: Sequence[T], weights: Sequence[float]) -> T:
        if len(items) != len(weights) or not items:
            raise ValueError("items and weights must be non-empty and of equal length")
        total = float(sum(weights))
        if total <= 0:
            raise ValueError("weights must sum to > 0")
        target = self.random() * total
        cumulative = 0.0
        for item, weight in zip(items, weights, strict=True):
            cumulative += weight
            if target < cumulative:
                return item
        return items[-1]

    def shuffle[T](self, items: MutableSequence[T]) -> None:
        for i in range(len(items) - 1, 0, -1):
            j = self.randbelow(i + 1)
            items[i], items[j] = items[j], items[i]

    def sample[T](self, items: Sequence[T], k: int) -> list[T]:
        if not 0 <= k <= len(items):
            raise ValueError("sample larger than population")
        pool = list(items)
        for i in range(k):
            j = i + self.randbelow(len(pool) - i)
            pool[i], pool[j] = pool[j], pool[i]
        return pool[:k]

    def bytes(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("n must be >= 0")
        if n == 0:
            return b""
        return self._rng.getrandbits(8 * n).to_bytes(n, "little")

    def hex(self, n_chars: int) -> str:
        return self.bytes((n_chars + 1) // 2).hex()[:n_chars]
