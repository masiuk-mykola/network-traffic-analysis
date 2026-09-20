from collections import Counter

import pytest

from capture_api.world.rng import Stream, stable_int, stream_digest


def test_same_seed_and_keys_give_the_same_sequence() -> None:
    a, b = Stream("demo", "block", "hq-core", 7), Stream("demo", "block", "hq-core", 7)
    assert [a.bits(64) for _ in range(20)] == [b.bits(64) for _ in range(20)]


def test_different_seed_or_keys_differ() -> None:
    base = [Stream("demo", "x").bits(64) for _ in range(1)]
    assert base != [Stream("alpha", "x").bits(64)]
    assert base != [Stream("demo", "y").bits(64)]
    assert stream_digest("demo", 1, 2) != stream_digest("demo", "1|2", "")


def test_golden_values_pin_the_algorithm() -> None:
    s = Stream("demo", "golden", 1)
    assert [s.randint(0, 1000) for _ in range(5)] == [833, 768, 573, 563, 150]
    assert s.bytes(8).hex() == "60dc66cae523c333"
    assert round(s.random(), 12) == 0.735854857283
    assert stable_int("demo", "x") == 4625050886780920813


def test_fork_is_equivalent_to_extended_keys() -> None:
    parent = Stream("demo", "incident")
    assert parent.fork("c2", 3).bits(64) == Stream("demo", "incident", "c2", 3).bits(64)
    assert parent.keys == ("incident",)
    assert parent.seed == "demo"


def test_helpers_respect_bounds() -> None:
    s = Stream("demo", "bounds")
    values = [s.randint(3, 7) for _ in range(2000)]
    assert set(values) == {3, 4, 5, 6, 7}
    floats = [s.uniform(-1.0, 1.0) for _ in range(1000)]
    assert all(-1.0 <= f < 1.0 for f in floats)
    assert all(0.0 <= s.random() < 1.0 for _ in range(1000))
    assert all(90 <= s.jitter(100, 0.1) < 110 for _ in range(200))
    normals = [s.approx_normal(10, 2) for _ in range(2000)]
    assert 9.7 < sum(normals) / len(normals) < 10.3


def test_choice_weighted_shuffle_sample() -> None:
    s = Stream("demo", "choices")
    items = ["a", "b", "c"]
    assert {s.choice(items) for _ in range(200)} == set(items)
    counts = Counter(s.weighted_choice(items, [0.0, 1.0, 3.0]) for _ in range(4000))
    assert counts["a"] == 0
    assert 2.5 < counts["c"] / counts["b"] < 3.5
    deck = list(range(20))
    s.shuffle(deck)
    assert sorted(deck) == list(range(20))
    assert deck != list(range(20))
    picked = s.sample(range(10), 4)
    assert len(set(picked)) == 4
    assert s.sample(range(3), 0) == []


def test_bytes_and_hex() -> None:
    s = Stream("demo", "bytes")
    assert s.bytes(0) == b""
    assert len(s.bytes(1000)) == 1000
    assert len(s.hex(5)) == 5
    assert s.bits(0) == 0


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.randbelow(0),
        lambda s: s.randint(5, 4),
        lambda s: s.bits(-1),
        lambda s: s.bytes(-1),
        lambda s: s.sample([1], 2),
        lambda s: s.weighted_choice([1], [0.0]),
        lambda s: s.weighted_choice([1, 2], [1.0]),
    ],
)
def test_invalid_arguments(call: object) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        call(Stream("demo", "bad"))  # type: ignore[operator]


def test_choice_on_empty_sequence() -> None:
    with pytest.raises(IndexError):
        Stream("demo").choice([])


def test_stable_int_bits() -> None:
    assert 0 <= stable_int("demo", "k", bits=8) < 256
    with pytest.raises(ValueError, match="bits"):
        stable_int("demo", bits=0)
