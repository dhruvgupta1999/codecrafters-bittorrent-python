import pytest

from app.main import bencode_data


def test_valid_string_bencoding():
    assert bencode_data(b"hello") == b"5:hello"
    assert bencode_data(b"hello world") == b"11:hello world"
    assert bencode_data(b"http://abc.com/announce") == b"23:http://abc.com/announce"


def test_valid_int_encoding():
    assert bencode_data(1401538053) == b"i1401538053e"
    assert bencode_data(-100) == b"i-100e"


def test_valid_list_encoding_no_nesting():
    assert bencode_data([1401538053]) == b"li1401538053ee"
    assert bencode_data([b"hello"]) == b"l5:helloe"
    assert bencode_data([b"hello", 1401538053, b"hello"]) == b"l5:helloi1401538053e5:helloe"


def test_valid_list_encoding_with_nesting():
    """"""
    assert bencode_data([[777, b"pear"]]) == b"lli777e4:pearee"
    assert bencode_data([b"hello", [b"hello", [b"hello"]]]) == b"l5:hellol5:hellol5:helloeee"
    assert bencode_data([[777, b"pear"], [b"hello"]]) == b"lli777e4:pearel5:helloee"


def test_valid_dict_encoding():
    """
    Output is sorted by key.
    """
    assert bencode_data({b"hello": 52}) == b"d5:helloi52ee"
    assert bencode_data({b"foo": b"bar", b"apple": b"fruit", b"100": 21}) == b'd3:100i21e5:apple5:fruit3:foo3:bare'
    assert bencode_data({b"name": b"alice", b"age": 25}) == b'd3:agei25e4:name5:alicee'
