import hashlib
import json
import sys
import re
import logging
from typing import Any

logging.basicConfig(level=logging.INFO)

# import bencodepy - available if you need it!
# import requests - available if you need it!

PIECE_HASH_LEN_BYTES = 20

def bencode_data(my_data: Any) -> bytes:
    """
    Binary encode data.
    """
    result = b''

    if isinstance(my_data, dict):
        sub_results = []
        for k in sorted(my_data):
            v = my_data[k]
            sub_results.extend([bencode_data(k), bencode_data(v)])

        return b'd' + b''.join(sub_results) + b'e'

    if isinstance(my_data, list):
        sub_results = []
        for item in my_data:
            sub_results.append(bencode_data(item))

        return b'l' + b''.join(sub_results) + b'e'

    if isinstance(my_data, str):
        return str(len(my_data)).encode() + b':' + my_data.encode()

    if isinstance(my_data, int):
        return b'i' + str(my_data).encode() + b'e'

    # If my_data is bytes type. That means it's a string in the tor file.
    # Return it in format "length:content"
    if isinstance(my_data, bytes):
        return str(len(my_data)).encode() + b':' + my_data

    raise TypeError(f"Unexpected type of param: {my_data} of type {type(my_data)}")


def get_info_sha_hash(info: dict):
    bencoded_info = bencode_data(info)
    sha1_hash = hashlib.sha1(bencoded_info).hexdigest()
    return sha1_hash


def _find_cur_element_end(elem_str):
    # find next 'e' which indicates END of current element only.
    e_idx = elem_str.find(b'e')
    if e_idx == -1:
        raise ValueError("Invalid encoded value")
    return e_idx


def _decode_bencode(bencoded_value: bytes, _is_list=False, _is_dict=False) -> tuple[Any, bytes]:
    """
    Decodes a bencoded value (used in BitTorrent metadata).
    Supports strings, integers, lists, and dictionaries.

    Example Inputs:
        b'4:pear' => 'pear'
        b'i52e' => 52
        b'li777e4:peare' => [777, 'pear']
        b'lli777e4:pearee' => [[777,"pear"]]
        b'd5:helloi52ee' => {'hello': 52}

    Note:
        Remember that bencoded strings are not actually strings, they are bytes of specified length.
        They can contain \x00 char.
        Because of this it is not always possible that bytes_obj.decode() gives an error saying that decoding
        to UTF is not possible.
    """
    s = bencoded_value
    result = []

    while s:
        if re.match(rb'^\d', s):  # Case: String (starts with a digit)
            colon_idx = s.find(b':')
            if colon_idx == -1:
                raise ValueError("Invalid encoded value: Missing colon in string encoding")

            length_of_elem = int(s[:colon_idx])
            # eg: 12:sjdfhsldkfjghfd  => 2 + 1 = 3 is the content start idx.
            content_start_idx = colon_idx + 1
            elem_content = s[content_start_idx: content_start_idx + length_of_elem]

            if len(elem_content) != length_of_elem:
                raise ValueError("Invalid encoded value: Incorrect string length")

            result.append(elem_content)
            s = s[content_start_idx + length_of_elem:]  # Move to next element

            logging.info(f"{bencoded_value=}\n{s=}\n")

        elif s.startswith(b'i'):  # Case: Integer (starts with 'i')
            end_idx = _find_cur_element_end(s)
            int_content = int(s[1:end_idx])
            result.append(int_content)
            s = s[end_idx + 1:]  # Skip 'e' and move to the next element

            logging.info(f"{bencoded_value=}\n{s=}")

        elif s.startswith(b'l'):  # Case: List (starts with 'l')
            elems_list, s = _decode_bencode(s[1:], _is_list=True)
            result.append(elems_list)
            logging.info(f"{bencoded_value=}\n{s=}")

        elif s.startswith(b'd'):  # Case: Dictionary (starts with 'd')
            elems_dict, s = _decode_bencode(s[1:], _is_dict=True)
            result.append(elems_dict)
            logging.info(f"{bencoded_value=}\n{s=}")

        elif s.startswith(b'e'):  # Case: End of list or dictionary
            s = s[1:]
            break

        else:
            logging.info(f"{bencoded_value=}\n{s=}")
            raise ValueError("Invalid encoded value: Unrecognized format")

    if _is_list:
        return result, s

    if _is_dict:
        # The dict can't have odd number of elements, as key:val * n = 2*n
        if len(result) % 2:
            raise ValueError("Invalid encoded value: Dictionary must have even number of elements (key-value pairs)")
        return {result[i]: result[i + 1] for i in range(0, len(result), 2)}, s

    return result[0] if result else None, s


def decode_bencode(bencoded_value: bytes):
    return _decode_bencode(bencoded_value)[0]


def main():
    command = sys.argv[1]

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    if command == "decode":
        # DO NOT CHANGE THIS PART. IT REPRESENTS A BINARY STRING COMING FROM A N/W CONNECTION.
        bencoded_value = sys.argv[2].encode()

        # json.dumps() can't handle bytes, but bencoded "strings" need to be
        # bytestrings since they might contain non utf-8 characters.
        #
        # Let's convert them to strings for printing to the co
        # nsole.
        def bytes_to_str(data):
            if isinstance(data, bytes):
                return data.decode()
            if isinstance(data, list):
                return [bytes_to_str(elem) for elem in data]
            if isinstance(data, dict):
                return {bytes_to_str(k): bytes_to_str(v) for k,v in data.items()}
            if isinstance(data, int|str):
                return data

            raise TypeError(f"Type not serializable: {type(data)}")

        # Convert bytes type to str type.
        print(json.dumps(bytes_to_str(decode_bencode(bencoded_value)), default=bytes_to_str))
    elif command == 'info':
        tor_file_path = sys.argv[2]
        bencoded_value = b''
        with open(tor_file_path, 'rb') as tor_file:
            """
            Tor file format
            
            contains a bencoded dictionary with the following keys and values:
            
            announce:
            URL to a "tracker", which is a central server that keeps track of peers participating in the sharing of a torrent.
            
            info:
            A dictionary with keys:
            - length: size of the file in bytes, for single-file torrents
            - name: suggested name to save the file / directory as
            - piece length: number of bytes in each piece
            - pieces: concatenated SHA-1 hashes of each piece as a string.
                        Each hash is 20 bytes long.
            """
            bencoded_value = tor_file.read()
            logging.info(f'tor file datatype: {type(bencoded_value)}')
            logging.info(f'tor file data as str: {str(bencoded_value)}')
            decoded_val = decode_bencode(bencoded_value)
            logging.info(f"decoded tor file: {decoded_val}")
            # The 'announce' field has the tracker url.
            print(f'Tracker URL: {decoded_val[b'announce'].decode()}')
            print(f'Length: {decoded_val[b'info'][b'length']}')
            # Check x = inv_f(f(x))
            assert decoded_val[b'info'] == decode_bencode(bencode_data(decoded_val[b'info']))
            print(f'Info Hash: {get_info_sha_hash(decoded_val[b'info'])}')
            print(f'Piece Length: {decoded_val[b'info'][b'piece length']}')
            print(f'Piece Hashes:')

            piece_hashes = []
            concat_hashes = decoded_val[b'info'][b'pieces']
            for i in range(0, len(concat_hashes), PIECE_HASH_LEN_BYTES):
                # Convert the 20 bytes to hexstring form to get the SHA hash in human readable form.
                sha_hash_as_hex = ''.join('{:02x}'.format(x) for x in concat_hashes[i:i+PIECE_HASH_LEN_BYTES])
                piece_hashes.append(sha_hash_as_hex)

            print('\n'.join(piece_hashes))

    else:
        raise NotImplementedError(f"Unknown command {command}")


if __name__ == "__main__":
    main()
