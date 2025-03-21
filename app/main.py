import json
import sys
import re
import logging
from typing import Any

logging.basicConfig(level=logging.INFO)

# import bencodepy - available if you need it!
# import requests - available if you need it!

def find_list_end(s):
    if len(s) < 2:
        raise ValueError("Invalid encoded value")
    count_ints = 0
    for idx, ch in enumerate(s):
        if ch == 'e' :
            if count_ints:
                count_ints -= 1
            else:
                return idx
        if ch == 'i':
            count_ints += 1
    raise ValueError("Invalid encoded value")


def find_cur_element_end(elem_str):
    # find next 'e' which indicates END of current element only.
    e_idx = elem_str.find('e')
    if e_idx == -1:
        raise ValueError("Invalid encoded value")
    return e_idx


def _decode_bencode(bencoded_value: str, _is_list=False, _is_dict=False) -> [Any, int]:
    """


    list within list is also possible.
    eg:
    lli777e4:pearee
    [[777,"pear"]]

    can handle dicts also:
    eg:
    dl5:helloei52ee
    {['hello]: 52}

    """
    result = []

    s = bencoded_value

    while s:

        match s:
            case s if re.match(r'^\d', s):  # First character is a digit
                colon_idx = s.find(':')
                if colon_idx == -1:
                    raise ValueError("Invalid encoded value")

                length_of_elem = int(s[:colon_idx])
                # eg: 12:sjdfhsldkfjghfd  => 2 + 1 = 3 is the content start idx.
                content_start_idx = colon_idx + 1
                elem_content = s[content_start_idx: content_start_idx+length_of_elem]
                if len(elem_content) != length_of_elem:
                    raise ValueError("Invalid encoded value")
                result.append(elem_content)
                # update s to next element
                s = s[content_start_idx+length_of_elem:]

                logging.info(f"{bencoded_value=}\n{s=}\n")

            case s if s[0] == 'i':  # Starts with 'i'
                end_idx = find_cur_element_end(s)
                int_content = s[1:end_idx]
                result.append(int(int_content))
                # next element comes after the 'e'.
                # update s to start from there.
                s = s[end_idx+1:]

                logging.info(f"{bencoded_value=}\n{s=}")

            case s if s[0] == 'l': # Starts with 'l'

                elems_list, s =  _decode_bencode(s[1:] ,_is_list=True)
                result.append(elems_list)
                logging.info(f"{bencoded_value=}\n{s=}")

            case s if s[0] == 'd':

                elems_dict, s = _decode_bencode(s[1:], _is_dict=True)
                result.append(elems_dict)
                logging.info(f"{bencoded_value=}\n{s=}")

            case s if s[0] == 'e':
                # This means that this is an end of a list. Return the result
                s = s[1:]
                break

            case _:
                logging.info(f"{bencoded_value=}\n{s=}")
                raise ValueError("Invalid encoded value")


    if _is_list:
        return result, s
    if _is_dict:
        if len(result) % 2:
            raise ValueError("Invalid encoded value")
        return { result[i]:result[i+1] for i in range(0,len(result),2) }, s

    return result[0], s

def decode_bencode(bencoded_value: str):
    return _decode_bencode(bencoded_value)[0]


# Examples:
#
# - decode_bencode(b"5:hello") -> b"hello"
# - decode_bencode(b"10:hello12345") -> b"hello12345"
def decode_bencode_old(bencoded_value: bytes):

    result = ''
    s = bencoded_value.decode()
    match s:
        case s if re.match(r'^\d', s):  # First character is a digit
            logging.info("First character is a digit.")
            length_str, content = (s.split(':', 1) + [None])[:2]
            if not content:
                raise ValueError("Invalid encoded value")
            result = content
        case s if re.match(r'^i.*e$', s):  # Starts with 'i', ends with 'e'
            logging.info("Starts with 'i' and ends with 'e'.")
            content = s[1:-1]
            result = int(content)
        case s if re.match(r'^l.*e$', s): # Starts with 'l', ends with 'e'
            logging.info("Starts with 'l' and ends with 'e'. (list)")


        case _:
            raise NotImplementedError("Only strings are supported at the moment")

    return result




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

            raise TypeError(f"Type not serializable: {type(data)}")

        # Uncomment this block to pass the first stage
        bencoded_value = bencoded_value.decode()
        print(json.dumps(decode_bencode(bencoded_value), default=bytes_to_str))
    else:
        raise NotImplementedError(f"Unknown command {command}")


if __name__ == "__main__":
    main()
