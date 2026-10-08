import pytest

from app.agent.amounts import parse_amount_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10198", 10198.0),
        ("$10.198", 10198.0),
        ("10.198,50", 10198.5),
        ("1.500,50", 1500.5),
        ("1500,5", 1500.5),
        ("12.5", 12.5),
        ("1.234.567", 1234567.0),
        ("20 lucas", 20000.0),
        ("20 luca", 20000.0),
        ("2k", 2000.0),
        ("2 K", 2000.0),
        ("1.5k", 1500.0),
        ("20 mil", 20000.0),
        ("un palo", 1000000.0),
        ("1,5 palos", 1500000.0),
        ("2 millones", 2000000.0),
        ("100 dólares", 100.0),
        ("abc", None),
        ("", None),
        (None, None),
        ("0", None),
        ("-5", None),
    ],
)
def test_parse_amount_text(raw, expected):
    assert parse_amount_text(raw) == expected
