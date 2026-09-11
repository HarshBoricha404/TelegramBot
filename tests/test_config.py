from __future__ import annotations

import pytest

from src.config import load_min_gain_pct


def test_empty_min_gain_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIN_GAIN_PCT", "")
    assert load_min_gain_pct() == 10


@pytest.mark.parametrize("value", ["not-a-number", "-1", "101"])
def test_invalid_min_gain_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("MIN_GAIN_PCT", value)
    with pytest.raises(ValueError):
        load_min_gain_pct()
