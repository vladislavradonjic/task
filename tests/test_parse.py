import pytest
from task.parse import parse_filter, parse_modification
from task.models import ParsedFilter, ParsedModification


# ---------------------------------------------------------------------------
# parse_filter
# ---------------------------------------------------------------------------

def test_filter_empty():
    assert parse_filter([]) == ParsedFilter()


def test_filter_single_id():
    result = parse_filter(["3"])
    assert result.ids == [3]
    assert result.tags == []
    assert result.properties == {}


def test_filter_multiple_ids():
    result = parse_filter(["1", "2", "3"])
    assert result.ids == [1, 2, 3]


def test_filter_positive_tag():
    result = parse_filter(["+bug"])
    assert result.tags == ["+bug"]


def test_filter_negative_tag():
    result = parse_filter(["-bug"])
    assert result.tags == ["-bug"]


def test_filter_multiple_tags():
    result = parse_filter(["+bug", "-feature"])
    assert result.tags == ["+bug", "-feature"]


def test_filter_property():
    result = parse_filter(["project:work"])
    assert result.properties == {"project": "work"}


def test_filter_property_empty_value():
    result = parse_filter(["due:"])
    assert result.properties == {"due": None}


def test_filter_property_value_with_colon():
    # value is everything after the first colon
    result = parse_filter(["note:foo:bar"])
    assert result.properties == {"note": "foo:bar"}


def test_filter_mixed():
    result = parse_filter(["1", "2", "+bug", "project:work", "due:"])
    assert result.ids == [1, 2]
    assert result.tags == ["+bug"]
    assert result.properties == {"project": "work", "due": None}


def test_filter_unknown_tokens_ignored(capsys):
    # unknown tokens are dropped and a notice is printed
    result = parse_filter(["notanid", "not-a-tag"])
    assert result == ParsedFilter()
    captured = capsys.readouterr()
    assert "notanid" in captured.out or "notanid" in captured.err
    assert "not-a-tag" in captured.out or "not-a-tag" in captured.err


def test_filter_tag_name_must_start_with_letter():
    # "+1tag" starts with a digit after the sign — not a valid tag; ignored
    result = parse_filter(["+1tag"])
    assert result.tags == []


# ---------------------------------------------------------------------------
# parse_modification
# ---------------------------------------------------------------------------

def test_modification_empty():
    assert parse_modification([]) == ParsedModification()


def test_modification_positive_tag():
    result = parse_modification(["+feature"])
    assert result.tags == ["+feature"]
    assert result.description == ""


def test_modification_negative_tag():
    result = parse_modification(["-today"])
    assert result.tags == ["-today"]


def test_modification_property():
    result = parse_modification(["priority:H"])
    assert result.properties == {"priority": "H"}
    assert result.description == ""


def test_modification_property_empty_value_means_removal():
    result = parse_modification(["wait:"])
    assert result.properties == {"wait": None}


def test_modification_description_single_word():
    result = parse_modification(["buy", "milk"])
    assert result.description == "buy milk"
    assert result.tags == []
    assert result.properties == {}


def test_modification_description_preserves_order():
    result = parse_modification(["do", "the", "thing"])
    assert result.description == "do the thing"


def test_modification_mixed():
    result = parse_modification(["Buy", "milk", "+grocery", "due:tomorrow", "project:home"])
    assert result.description == "Buy milk"
    assert result.tags == ["+grocery"]
    assert result.properties == {"due": "tomorrow", "project": "home"}


def test_modification_integers_are_description_words():
    # bare integers in modify section land in description, not an ID list
    result = parse_modification(["depends", "3,4"])
    assert result.description == "depends 3,4"
    assert result.tags == []
    assert result.properties == {}
