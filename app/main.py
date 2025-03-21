import json
import sys
import re
import logging

logging.basicConfig(level=logging.INFO)

# import bencodepy - available if you need it!
# import requests - available if you need it!

# Examples:
#
# - decode_bencode(b"5:hello") -> b"hello"
# - decode_bencode(b"10:hello12345") -> b"hello12345"
def decode_bencode(bencoded_value: bytes):

    result = ''
    s = bencoded_value.decode()
    match s:
        case s if re.match(r'^\d', s):  # First character is a digit
            logging.info("First character is a digit.")
            length_str, content = (s.rsplit(':', 1) + [None])[:2]
            if not content:
                raise ValueError("Invalid encoded value")
            result = content
        case s if re.match(r'^i.*e$', s):  # Starts with 'i', ends with 'e'
            logging.info("Starts with 'i' and ends with 'e'.")
            content = s[1:-1]
            result = int(content)
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
        decoded_val = decode_bencode(bencoded_value)
        # print(decoded_val)
        print(json.dumps(decode_bencode(bencoded_value), default=bytes_to_str))
    else:
        raise NotImplementedError(f"Unknown command {command}")


if __name__ == "__main__":
    main()
