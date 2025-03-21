import pytest
import re

from app.main import decode_bencode


def test_valid_string_decoding():
    assert decode_bencode(b"5:hello") == "hello"
    assert decode_bencode(b"11:hello world") == "hello world"
    assert decode_bencode(b"23:http://abc.com/announce") == "http://abc.com/announce"

def test_invalid_string_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"5hello")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"5:")

def test_valid_int_decoding():
    assert decode_bencode(b"i1401538053e") == 1401538053
    assert decode_bencode(b"i-100e") == -100

def test_valid_list_decoding():
    assert decode_bencode(b"li1401538053ee") == [1401538053]
    assert decode_bencode(b"l5:helloe") == ["hello"]
    assert decode_bencode(b"l5:helloi1401538053e5:helloe") == ["hello",1401538053,"hello"]


def test_unsupported_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"bencoded")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"i123x")
