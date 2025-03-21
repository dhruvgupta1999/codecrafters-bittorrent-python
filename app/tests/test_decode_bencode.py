import pytest
import re

from app.main import decode_bencode

def test_valid_string_decoding():
    assert decode_bencode("5:hello") == "hello"
    assert decode_bencode("11:hello world") == "hello world"
    assert decode_bencode("23:http://abc.com/announce") == "http://abc.com/announce"

def test_invalid_string_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("5hello")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("5:")

def test_valid_int_decoding():
    assert decode_bencode("i1401538053e") == 1401538053
    assert decode_bencode("i-100e") == -100

def test_valid_list_decoding_no_nesting():
    assert decode_bencode("li1401538053ee") == [1401538053]
    assert decode_bencode("l5:helloe") == ["hello"]
    assert decode_bencode("l5:helloi1401538053e5:helloe") == ["hello", 1401538053, "hello"]


def test_valid_list_decoding_with_nesting():
    assert decode_bencode("lli777e4:pearee") == [[777,"pear"]]
    assert decode_bencode("l5:hellol5:hellol5:helloeee") == ["hello",['hello', ['hello']]]
    assert decode_bencode("lli777e4:pearel5:helloee") == [[777,"pear"],['hello']]

def test_valid_dict_decoding():
    assert decode_bencode("d5:helloi52ee") == {"hello": 52}
    assert decode_bencode("d3:foo3:bar5:apple5:fruiti100ei21ee") == {"foo": "bar", "apple": "fruit", 100: 21}
    assert decode_bencode("d4:name5:alice3:agei25ee") == {"name": "alice", "age": 25}

def test_invalid_dict_decoding():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("d5:hello5:worldi10e")  # Odd number of elements
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("d5:hello")  # No closing 'e'

def test_unsupported_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("bencoded")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("i123x")
