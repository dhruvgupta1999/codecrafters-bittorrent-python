import pytest
import re

from app.main import decode_bencode


def test_valid_string_decoding():
    assert decode_bencode("5:hello") == b"hello"
    assert decode_bencode("11:hello world") == b"hello world"

def test_valid_int_decoding():
    assert decode_bencode("i52e") == b"52"
    assert decode_bencode("i-100e") == b"-100"

def test_invalid_string_format():
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("5hello")
    with pytest.raises(ValueError, match="Invalid encoded value"):
        decode_bencode("5:")

def test_unsupported_format():
    with pytest.raises(NotImplementedError, match="Only strings are supported at the moment"):
        decode_bencode("bencoded")
        with pytest.raises(NotImplementedError, match="Only strings are supported at the moment"):
            decode_bencode("i123x")
