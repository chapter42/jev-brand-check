import asyncio
from types import SimpleNamespace

import httpx2
import pytest
from typesafe_sdk import TypeSafeAuthenticationError, TypeSafeRateLimitError

from brand_check import (
    annotate,
    build_pattern,
    judge_rows,
    parse_spellings,
    read_csv,
    summarize,
    to_csv,
)


class FakeClient:
    """Stands in for AsyncTypeSafeClient; returns fixed probabilities or raises."""

    def __init__(self, mentioned=0.9, recommended=0.8, error=None):
        self.answers = {"mentioned": mentioned, "recommended": recommended}
        self.error = error
        self.calls = 0

    async def system_one(self, state, questions):
        self.calls += 1
        await asyncio.sleep(0.01)  # like a real network call, gives other tasks a turn
        if self.error:
            raise self.error
        return SimpleNamespace(nouls={k: SimpleNamespace(noul=v) for k, v in self.answers.items()})


def make_error(cls, status):
    return cls(status, {}, httpx2.Headers(), message="fake")


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_read_csv_sniffs_delimiter(delimiter):
    data = f"prompt{delimiter}response\nq1{delimiter}\"a, b; c\"\n".encode()
    columns, rows, found = read_csv(data)
    assert columns == ["prompt", "response"]
    assert rows[0]["response"] == "a, b; c"
    assert found == delimiter


def test_read_csv_strips_bom():
    columns, _, _ = read_csv("﻿prompt,response\nq,a\n".encode())
    assert columns[0] == "prompt"


def test_parse_spellings():
    assert parse_spellings(" Nova, nova.nl ,, ") == ["Nova", "nova.nl"]
    assert parse_spellings("  ") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Koop het bij Nova.", True),
        ("Bestel via nova.nl vandaag", True),
        ("NOVA is snel", True),
        ("Een innovatieve aanpak", False),
        ("Kijk bij Orbit", False),
    ],
)
def test_pattern_whole_words(text, expected):
    assert bool(build_pattern(["nova", "nova.nl"]).search(text)) is expected


def test_pattern_with_punctuation():
    pattern = build_pattern(["A&B"])
    assert pattern.search("Probeer A&B of Orbit.")
    assert not pattern.search("XA&BC")


def test_judge_rows_prefilter_and_empty():
    rows = [{"r": "Nova is top"}, {"r": "Orbit is top"}, {"r": "  "}]
    client = FakeClient()
    results = asyncio.run(judge_rows(client, rows, "nova", build_pattern(["nova"]), "r", 2))
    assert client.calls == 1
    assert results[0] == {"mentioned": 0.9, "recommended": 0.8, "sent": True}
    assert results[1] == {"mentioned": 0.0, "recommended": 0.0, "sent": False}
    assert results[2] == {"error": "empty answer"}


def test_judge_rows_keeps_going_on_other_errors():
    rows = [{"r": "nova"}, {"r": "nova"}]
    client = FakeClient(error=make_error(TypeSafeRateLimitError, 429))
    results = asyncio.run(judge_rows(client, rows, "nova", build_pattern(["nova"]), "r", 1))
    assert all(r["error"].startswith("TypeSafeRateLimitError") for r in results)


def test_judge_rows_stops_on_invalid_key():
    rows = [{"r": "nova"}] * 20
    client = FakeClient(error=make_error(TypeSafeAuthenticationError, 401))
    with pytest.raises(TypeSafeAuthenticationError):
        asyncio.run(judge_rows(client, rows, "nova", build_pattern(["nova"]), "r", 1))
    assert client.calls < len(rows)


def test_annotate_summarize_and_export():
    rows = [{"r": "a"}, {"r": "b"}, {"r": "c"}, {"r": ""}]
    results = [
        {"mentioned": 0.95, "recommended": 0.6, "sent": True},
        {"mentioned": 0.9, "recommended": 0.1, "sent": True},
        {"mentioned": 0.0, "recommended": 0.0, "sent": False},
        {"error": "empty answer"},
    ]
    annotated = annotate(rows, results, 0.5)
    assert annotated[0]["jev_recommended"] == "yes"
    assert annotated[2]["jev_sent"] == "no (brand not in text)"
    assert annotated[2]["jev_mentioned_p"] == ""
    assert annotated[3]["jev_error"] == "empty answer"
    assert "jev_sent" not in rows[0]  # input rows stay untouched

    assert summarize(results, 0.5) == {
        "judged": 3, "errors": 1, "sent": 2, "mentioned": 2, "recommended": 1, "unsure": 1,
    }
    assert summarize(results, 0.7)["recommended"] == 0

    exported = to_csv(["r"], annotated, ";")
    assert exported.splitlines()[0].startswith("r;jev_sent;")
