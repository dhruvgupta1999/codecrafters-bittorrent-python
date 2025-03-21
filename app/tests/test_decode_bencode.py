import pytest
import re

from app.main import decode_bencode


def test_valid_string_decoding():
    assert decode_bencode(b"5:hello") == "hello"
    assert decode_bencode(b"11:hello world") == "hello world"

def test_valid_int_decoding():
    assert decode_bencode(b"i1401538053e") == "1401538053"
    assert decode_bencode(b"i-100e") == "-100"

def test_invalid_string_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"5hello")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode(b"5:")

def test_unsupported_format():
    with pytest.raises(NotImplementedError, match="Only strings are supported at the moment"):
        decode_bencode(b"bencoded")
        with pytest.raises(NotImplementedError, match="Only strings are supported at the moment"):
            decode_bencode(b"i123x")
