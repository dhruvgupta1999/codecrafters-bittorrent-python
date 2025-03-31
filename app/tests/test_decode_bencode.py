import pytest
import re

from app.main import decode_bencode

def test_valid_string_decoding():
    assert decode_bencode(b"5:hello") == b"hello"
    assert decode_bencode(b"11:hello world") == b"hello world"
    assert decode_bencode(b"23:http://abc.com/announce") == b"http://abc.com/announce"

def test_invalid_string_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"5hello")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"5:")

def test_valid_int_decoding():
    assert decode_bencode(b"i1401538053e") == 1401538053
    assert decode_bencode(b"i-100e") == -100

def test_valid_list_decoding_no_nesting():
    assert decode_bencode(b"li1401538053ee") == [1401538053]
    assert decode_bencode(b"l5:helloe") == [b"hello"]
    assert decode_bencode(b"l5:helloi1401538053e5:helloe") == [b"hello", 1401538053, b"hello"]

def test_valid_list_decoding_with_nesting():
    assert decode_bencode(b"lli777e4:pearee") == [[777, b"pear"]]
    assert decode_bencode(b"l5:hellol5:hellol5:helloeee") == [b"hello", [b"hello", [b"hello"]]]
    assert decode_bencode(b"lli777e4:pearel5:helloee") == [[777, b"pear"], [b"hello"]]

def test_valid_dict_decoding():
    assert decode_bencode(b"d5:helloi52ee") == {b"hello": 52}
    assert decode_bencode(b"d3:foo3:bar5:apple5:fruiti100ei21ee") == {b"foo": b"bar", b"apple": b"fruit", 100: 21}
    assert decode_bencode(b"d4:name5:alice3:agei25ee") == {b"name": b"alice", b"age": 25}

def test_invalid_dict_decoding():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"d5:hello5:worldi10e")  # Odd number of elements
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"d5:hello")  # No closing 'e'

def test_unsupported_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"bencoded")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"i123x")
