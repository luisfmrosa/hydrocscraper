from discovery.store import FIELDS, with_digest
from utils.hashing import row_md5


def test_deterministic_and_order_sensitive():
    rec = {"a": "x", "b": "y"}
    assert row_md5(rec, ["a", "b"]) == row_md5(dict(rec), ["a", "b"])
    assert row_md5(rec, ["a", "b"]) != row_md5(rec, ["b", "a"])


def test_separator_prevents_collisions():
    assert row_md5({"a": "a", "b": "bc"}, ["a", "b"]) != row_md5({"a": "ab", "b": "c"}, ["a", "b"])


def test_none_and_lists():
    assert row_md5({"a": None}, ["a"]) == row_md5({}, ["a"]) == row_md5({"a": ""}, ["a"])
    assert row_md5({"c": ["NOR", "GBR"]}, ["c"]) == row_md5({"c": "NOR,GBR"}, ["c"])


def test_with_digest_ignores_existing_digest():
    rec = {f: f"v_{f}" for f in FIELDS}
    first = with_digest([rec])[0]
    again = with_digest([first])[0]
    assert first["md5_digest"] == again["md5_digest"] == row_md5(rec, FIELDS)
    assert "md5_digest" not in rec
