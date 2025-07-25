import functools
import hashlib
import json
import sys
import re
import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import socket


logging.basicConfig(level=logging.WARNING)

# import bencodepy - available if you need it!
# import requests - available if you need it!

# If test_flag is set, we may do certain things in code to make it easy to test.
TEST_FLAG = False
if TEST_FLAG:
    logging.warning("The TEST_FLAG is set...")


PIECE_HASH_LEN_BYTES = 20

def bencode_data(my_data: Any) -> bytes:
    """
    Encode a Python object into bencoded bytes, as used in the BitTorrent protocol.

    Supported types:
        - dict: Encoded as 'd<key><value>...e' with keys sorted lexicographically.
        - list: Encoded as 'l<item>...e'.
        - str: Encoded as '<length>:<string>' (UTF-8 bytes).
        - int: Encoded as 'i<integer>e'.
        - bytes: Encoded as '<length>:<bytes>' (raw bytes, not decoded).

    Args:
        my_data: The Python object to encode (dict, list, str, int, or bytes).

    Returns:
        bytes: The bencoded representation of the input.

    Raises:
        TypeError: If the input type is not supported for bencoding.
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



def _find_cur_element_end(elem_str):
    """
    Find the index of the next 'e' byte, which indicates the end of the current bencoded element.
    Raises ValueError if not found.
    """
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
    """
    Decode a bencoded value and return the decoded Python object.
    """
    return _decode_bencode(bencoded_value)[0]


def get_info_sha_hash(info: dict, as_hexadecimal=False):
    """
    Compute the SHA-1 hash of the bencoded info dictionary from a torrent file.
    Returns the hash as bytes (default) or as a hexadecimal string if as_hexadecimal is True.
    """
    bencoded_info = bencode_data(info)
    if as_hexadecimal:
        # 40 hexdigits, as 1 hexdigit is 4 bits.
        sha1_hash = hashlib.sha1(bencoded_info).hexdigest()
    else:
        # Return as bytes (20 bytes)
        sha1_hash = hashlib.sha1(bencoded_info).digest()
    return sha1_hash


def _send_get_request_to_tracker(decoded_val):
    """
    # Send a GET request with TOR file data.
    # The tracker which is a central node, will give you a peers list with the data.
    # explanation of what we are doing here: https://chatgpt.com/share/67f23bf1-5d84-8003-a390-81ed30e346fb


    Tracker response:

    The response will be a bencoded dictionary. It will have:

    interval: You can ignore this.
    peers:  A string of multiple 6-byte chunks.
            Each chunk = 4 bytes IP + 2 bytes port.
            You’ll have to split this string into 6-byte blocks and extract IP and port from each.
    """
    # See: \tor\app\url_encoding_bytes_data_readme for more on how bytes data is url encoded for GET request.
    import requests

    tracker_url = decoded_val[b'announce'].decode()
    params = {
        # requests module will automatically handle the url encoding for the info hash bytes.
        # Send only the info hash as ben
        "info_hash": get_info_sha_hash(decoded_val[b'info']),
        "peer_id": _get_peer_id(),
        "port": 6881,
        # I haven't uploaded anything
        "uploaded": 0,
        # you haven’t downloaded anything yet
        "downloaded": 0,
        # Set this to the total file size
        "left": decoded_val[b'info'][b'length'],
        # means "give me a compact list of peers"
        "compact": 1
    }
    response = requests.get(tracker_url, params=params)
    return response


def _read_tor_file(tor_file_path):
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
    return bencoded_value

def _get_peer_id(as_bytes=False):
    """
    Return a static peer ID for this client, as bytes or string depending on as_bytes.
    """
    # This is the peer id of my machine.
    if as_bytes:
        return b'a' * 20
    return 'a' * 20


def connect_to_peer(sha_hash_as_bytes, peer_ip):
    """
    Connect to a peer using TCP and perform the BitTorrent protocol handshake.
    Returns a tuple of (peer_ip, socket object) if successful, or (peer_ip, None) on failure.
    """
    # Can add a retry functionality.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(peer_ip)
        _tor_protocol_handshake_with_peer(sock, sha_hash_as_bytes)
    except:
        # If unable to connect for any reason, just return None.
        # We will just depend on other peers for this.
        return peer_ip, None
    return peer_ip, sock


def main():
    """
    Main entry point for the BitTorrent client. Parses command-line arguments and executes the requested command.

    Supported commands:
    - decode <bencoded_value>:
        Decodes a bencoded value from the command line and prints the resulting Python object as JSON.
    - info <torrent_file_path>:
        Reads a .torrent file, decodes its metadata, and prints tracker URL, file length, info hash, piece length, and all piece hashes.
    - peers <torrent_file_path>:
        Queries the tracker for the given .torrent file and prints a list of available peers (IP:port).
    - handshake <torrent_file_path> <peer_ip:peer_port>:
        Connects to a peer and performs the BitTorrent protocol handshake, printing the peer's ID on success.
    - download_piece -o <output_path> <torrent_file_path> <piece_index>:
        Downloads a specific piece from a peer and writes it to the given output file.
    - download -o <output_path> <torrent_file_path>:
        Downloads the entire file by fetching all pieces from available peers and writing them in order to the output file.

    Raises:
        NotImplementedError: If an unknown command is provided.
    """
    command = sys.argv[1]

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    if command == "decode":
        # DO NOT CHANGE THIS PART. IT REPRESENTS A BINARY STRING COMING FROM A N/W CONNECTION.
        bencoded_val = sys.argv[2].encode()

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
        print(json.dumps(bytes_to_str(decode_bencode(bencoded_val)), default=bytes_to_str))
    elif command == 'info':
        # Test this part using: python main.py info "C:\Users\Dhruv Gupta\codekrafter\tor\sample.torrent"
        tor_file_path = sys.argv[2]
        bencoded_tor_file = _read_tor_file(tor_file_path)
        decoded_tor_file = decode_bencode(bencoded_tor_file)
        logging.info(f"decoded tor file: {decoded_tor_file}")
        # The 'announce' field has the tracker url.
        print(f'Tracker URL: {decoded_tor_file[b'announce'].decode()}')
        print(f'Length: {decoded_tor_file[b'info'][b'length']}')
        # Check x = inverse_f(f(x))
        assert decoded_tor_file[b'info'] == decode_bencode(bencode_data(decoded_tor_file[b'info']))
        print(f'Info Hash: {get_info_sha_hash(decoded_tor_file[b'info'], as_hexadecimal=True)}')
        print(f'Piece Length: {decoded_tor_file[b'info'][b'piece length']}')
        print(f'Piece Hashes:')

        piece_hashes = []
        concat_hashes = decoded_tor_file[b'info'][b'pieces']
        for i in range(0, len(concat_hashes), PIECE_HASH_LEN_BYTES):
            # Convert the 20 bytes to hexstring form to get the SHA hash in human readable form.
            # Basically, each byte is converted one by one to a two digit hex. and all the hex values are concated.
            sha_hash_as_hex = ''.join('{:02x}'.format(x) for x in concat_hashes[i:i+PIECE_HASH_LEN_BYTES])
            piece_hashes.append(sha_hash_as_hex)

        print('\n'.join(piece_hashes))
    elif command == 'peers':
        tor_file_path = sys.argv[2]
        bencoded_tor_file = _read_tor_file(tor_file_path)
        decoded_tor_file = decode_bencode(bencoded_tor_file)
        logging.info(f"decoded tor file: {decoded_tor_file}")

        peer_ips = get_peer_ips_from_tracker(decoded_tor_file)
        for ip_str, port_number in peer_ips:
            print(f'{ip_str}:{port_number}')

    elif command == 'handshake':
        # """
        # Input command:
        # /your_bittorrent.sh handshake sample.torrent <peer_ip>:<peer_port>
        #
        #
        # """
        tor_file_path = sys.argv[2]
        peer_info = sys.argv[3]

        bencoded_tor_file = _read_tor_file(tor_file_path)
        decoded_tor_file = decode_bencode(bencoded_tor_file)
        logging.info(f"decoded tor file: {decoded_tor_file}")
        sha_hash_as_bytes = get_info_sha_hash(decoded_tor_file[b'info'])


        ip, port = peer_info.split(':')
        port = int(port)
        peer_ip = ip, port
        peer_ip, sock = connect_to_peer(sha_hash_as_bytes, peer_ip)
        sock.close()


    elif command == 'download_piece':
        """
        $ ./your_program.sh download_piece -o /tmp/test-piece sample.torrent <piece_index>
        """
        piece_download_file_path = sys.argv[3]
        tor_file_path = sys.argv[4]
        cur_piece_index = int(sys.argv[5])
        bencoded_tor_file = _read_tor_file(tor_file_path)
        decoded_tor_file = decode_bencode(bencoded_tor_file)
        logging.info(f"decoded tor file: {decoded_tor_file}")
        sha_hash_as_bytes = get_info_sha_hash(decoded_tor_file[b'info'])


        # Get peers from tracker
        peer_ips = get_peer_ips_from_tracker(decoded_tor_file)

        # Handshake with a peer
        import socket

        # Create a TCP/IP socket
        tcp_sock_to_peer_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Connect to the server (this does the TCP handshake)
        # Here I just picked the first peer among list of peers (because every peer has every piece in this challenge).
        server_address = peer_ips[0]

        INTERESTED = 2
        REQUEST = 6
        try:
            tcp_sock_to_peer_server.connect(server_address)
            _tor_protocol_handshake_with_peer(tcp_sock_to_peer_server, sha_hash_as_bytes)
            # Wait for a bitfield message from the peer indicating which pieces it has
            # For this challenge, the assumption is that every peer has every piece.
            msg_type, payload = _recv_peer_msg(tcp_sock_to_peer_server)
            assert msg_type == 5
            # Send interested msg
            _send_peer_msg(tcp_sock_to_peer_server, msg_type=INTERESTED, payload=b'')
            # Wait for unchoke msg
            msg_type, payload = _recv_peer_msg(tcp_sock_to_peer_server)
            assert msg_type == 1
            cur_piece_bytes = get_cur_piece_bytes(cur_piece_index, decoded_tor_file)
            logging.info(f"{cur_piece_bytes=}")
            download_piece_and_write_to_file(REQUEST, tcp_sock_to_peer_server, cur_piece_bytes,
                                             cur_piece_index, piece_download_file_path)
        finally:
            tcp_sock_to_peer_server.close()

    elif command == 'download':
        """
        $ ./your_program.sh download -o /tmp/test-piece sample.torrent
        """
        piece_download_file_path = sys.argv[3]
        tor_file_path = sys.argv[4]
        bencoded_tor_file = _read_tor_file(tor_file_path)
        decoded_tor_file = decode_bencode(bencoded_tor_file)
        logging.info(f"decoded tor file: {decoded_tor_file}")
        sha_hash_as_bytes = get_info_sha_hash(decoded_tor_file[b'info'])


        # Get peers from tracker
        peer_ips = get_peer_ips_from_tracker(decoded_tor_file)
        # If TEST_FLAG IS SET, then only use 1 IP address. This may help in testing.
        # The challenge actually has all the pieces on each ip.
        if TEST_FLAG:
            logging.info("Using just 1 peer ip to dld the data.")
            peer_ips = peer_ips[:1]

        # Handshake with a peer
        # Create a TCP/IP socket for each peer_ip
        peer_ip_to_tcp_conn = {}

        # Parallely connect to all peers.
        with ThreadPoolExecutor() as executor:
            connect_to_peer_partial = functools.partial(connect_to_peer, sha_hash_as_bytes)
            results = executor.map(connect_to_peer_partial, peer_ips)
            for peer_ip, sock in results:
                if sock:
                    peer_ip_to_tcp_conn[peer_ip] = sock

        logging.info(f"num peers successfully connected: {len(peer_ip_to_tcp_conn)}")

        # Get mapping of which piece is available on what peers.
        num_pieces = get_num_pieces(decoded_tor_file)
        logging.info(f"{num_pieces=}")
        piece_to_peer_ips = get_piece_to_peer_ips(peer_ip_to_tcp_conn, num_pieces)

        # Now parallely download the pieces.
        INTERESTED = 2
        REQUEST = 6
        peer_ip_to_lock = {peer_ip: threading.Lock() for peer_ip in peer_ips}
        # We don't want to send INTERESTED msg repeatedly, so keep track of which peers we have
        # already told that we are INTERESTED.
        # Here I am using bool instead of any lock, cuz we are already in critical section when interested status is updated.
        peer_ip_to_interested_status = {peer_ip: False for peer_ip in peer_ips}
        # While recv() on peer, it can send you msg type 'choke' (0).
        # This means you are put on hold while the peer does other things.
        # In that case you need to wait for an 'unchoke' msg (1).
        # After sending INTERESTED msg, the first thing peer does is send you an unchoke msg.
        def parallel_wrapper_dld_piece(piece_idx):
            logging.info(f"parallel_wrapper_dld_piece() for {piece_idx=}")
            peer_ip_to_use = None
            # Keep retrying until we find a valid peer that we can use.
            while not peer_ip_to_use:
                for peer_ip in piece_to_peer_ips[piece_idx]:
                    if peer_ip_to_lock[peer_ip].acquire(blocking=False):
                        # We have acquired a connection.
                        logging.info(f"acquired peer_ip to dld {piece_idx=}")
                        peer_ip_to_use = peer_ip
                        break

            if not peer_ip_to_use:
                logging.error("Some issue in code, peer_ip is None")

            logging.info(f"Using {peer_ip_to_use} to fetch {piece_idx=}")
            peer_conn = peer_ip_to_tcp_conn[peer_ip_to_use]
            cur_piece_bytes = get_cur_piece_bytes(piece_idx, decoded_tor_file)
            logging.info(f"Num bytes in {piece_idx=} is {cur_piece_bytes}")
            try:
                if not peer_ip_to_interested_status[peer_ip_to_use]:
                    _send_peer_msg(peer_conn, msg_type=INTERESTED, payload=b'')
                    msg_type, payload = _recv_peer_msg(peer_conn)
                    logging.info(f"Waiting for unchoke, received {msg_type=}")
                    # Wait for unchoke msg
                    assert msg_type == 1
                    peer_ip_to_interested_status[peer_ip_to_use] = True
                piece_data = download_piece(REQUEST, peer_conn, cur_piece_bytes, piece_idx)
            finally:
                # Now that piece is downloaded, we can release the connection from busy state.
                peer_ip_to_lock[peer_ip_to_use].release()
                logging.info(f"released peer_ip to dld {piece_idx=}")
            return piece_idx, piece_data

        num_pieces = get_num_pieces(decoded_tor_file)
        piece_idx_to_piece_data = None
        with ThreadPoolExecutor() as executor:
            results = executor.map(parallel_wrapper_dld_piece, range(num_pieces))
            piece_idx_to_piece_data = dict(results)

        # peer_ip_to_use = peer_ips[0]
        # peer_conn = peer_ip_to_tcp_conn[peer_ip_to_use]
        # _send_peer_msg(peer_conn, msg_type=INTERESTED, payload=b'')
        # msg_type, payload = _recv_peer_msg(peer_conn)
        # logging.info(f"Waiting for unchoke, received {msg_type=}")
        # for piece_idx in range(num_pieces):
        #     cur_piece_bytes = get_cur_piece_bytes(piece_idx, decoded_tor_file)
        #     logging.info(f"Num bytes in {piece_idx=} is {cur_piece_bytes}")
        #     download_piece_and_write_to_file(REQUEST, peer_conn, cur_piece_bytes, piece_idx, piece_download_file_path)


        assert num_pieces == len(piece_idx_to_piece_data)
        # write to file
        with open(piece_download_file_path, 'ab') as f:
            # The block data starts at payload[8]
            for piece_idx in range(num_pieces):
                f.write(piece_idx_to_piece_data[piece_idx])


        # Close all connections
        for ip, conn in peer_ip_to_tcp_conn.items():
            conn.close()

    else:
        raise NotImplementedError(f"Unknown command {command}")


def get_piece_to_peer_ips(peer_ip_to_tcp_conn: dict, num_pieces) -> dict[int, list[tuple]]:
    """
    For each piece index, return a list of peer IPs that have that piece, based on bitfield messages from peers.
    """
    piece_to_peer_ips = defaultdict(list)
    for peer_ip, conn in peer_ip_to_tcp_conn.items():
        # IMPROV: try catch block around all tcp communications, so that we continue to operate other
        # peers even if comm with one fails.
        # Wait for a bitfield message from the peer indicating which pieces it has
        msg_type, payload = _recv_peer_msg(conn)
        if msg_type != 5:
            logging.warning(f"{peer_ip=} didn't send the expected bitfield message. "
                         f"msg_type received {msg_type=}")
        # Use the byte array to decode which pieces are present.
        # If b'1' then that piece idx is there, if b'0' then not there.
        logging.info(f"The bitset for {peer_ip=} is {payload}")
        piece_idx = 0
        for byte in payload:
            # Assuming left-to-right Endianness.
            # In every byte, start from MSb and move toward LSb.
            for _ in range(8):
                if byte & (1 << 7):
                    piece_to_peer_ips[piece_idx].append(peer_ip)
                else:
                    logging.info(f"{piece_idx=} not found on {peer_ip=}")
                # Move next lower bit as the MSb.
                byte = byte << 1
                piece_idx += 1
                if piece_idx >= num_pieces:
                    break
            if piece_idx >= num_pieces:
                break

    return piece_to_peer_ips


def get_peer_ips_from_tracker(decoded_tor_file) -> list[tuple[str, int]]:
    """
    Query the tracker and parse the response to extract a list of (ip, port) tuples for available peers.
    """
    response = _send_get_request_to_tracker(decoded_tor_file)
    logging.info(f"response status code: {response.status_code}")
    becoded_response_content = response.content
    decoded_content = decode_bencode(becoded_response_content)
    logging.info(f"decoded content: {decoded_content}")
    peers = decoded_content[b'peers']
    peer_ips = []
    IP_PORT_CHUNK_SIZE_BYTES = 6
    for i in range(0, len(peers), IP_PORT_CHUNK_SIZE_BYTES):
        ip_bytes, port_bytes = peers[i:i + 4], peers[i + 4:i + IP_PORT_CHUNK_SIZE_BYTES]
        # If IP bytes are 165 24 59 123 => 165.24.59.123
        ip_str = '.'.join(f'{b:d}' for b in ip_bytes)
        port_number = int.from_bytes(port_bytes, byteorder='big')
        peer_ips.append((ip_str, port_number))
        logging.info(f'{ip_str}:{port_number}')
    return peer_ips


def get_cur_piece_bytes(cur_piece_index, decoded_tor_file):
    """
    Return the number of bytes in the specified piece index, handling the last piece which may be shorter.
    Context:
    The data is divided into pieces, and each piece is a fixed length.
    The last piece may be shorter than the other pieces as it contains the remainder of the file.
    """
    # ALl pieces will have this tor_file[info][piece length] length, except the last piece which has only remainder length...
    piece_length = decoded_tor_file[b'info'][b'piece length']
    file_length = decoded_tor_file[b'info'][b'length']
    last_piece_length = file_length % piece_length
    is_last_piece = cur_piece_index == (file_length // piece_length)
    cur_piece_bytes = last_piece_length if is_last_piece else piece_length
    return cur_piece_bytes

def get_num_pieces(decoded_tor_file):
    """
    Return the total number of pieces in the torrent, based on file and piece length.
    """
    piece_length = decoded_tor_file[b'info'][b'piece length']
    file_length = decoded_tor_file[b'info'][b'length']
    last_piece_length = file_length % piece_length
    num_pieces = (file_length // piece_length) + (last_piece_length > 0)
    return num_pieces


def download_piece_and_write_to_file(REQUEST, client_socket, cur_piece_bytes, query_piece_index,
                                     piece_download_file_path):
    """
    Download a piece from a peer and write it to the specified file path.
    """
    piece = download_piece(REQUEST, client_socket, cur_piece_bytes, query_piece_index)
    with open(piece_download_file_path, 'ab') as f:
        f.write(piece)


def download_piece(REQUEST, peer_conn, query_piece_num_bytes, query_piece_index):
    """Returns the piece as byte string."""

    # Send request messages and receive 16kB blocks of the piece, till the piece is received completely.
    BLOCK_SIZE = int(2 ** 14)
    block_offset = 0
    piece = b''
    logging.info(f"Expected num bytes in piece: {query_piece_num_bytes}")
    while block_offset < query_piece_num_bytes:

        logging.info(f"{block_offset=}")
        block_len_to_downld = int(min(BLOCK_SIZE, query_piece_num_bytes - block_offset))
        logging.info(f"num bytes we are trying to dld: {block_len_to_downld}")
        payload = (query_piece_index.to_bytes(length=4) + block_offset.to_bytes(length=4) +
                   block_len_to_downld.to_bytes(length=4))

        _send_peer_msg(peer_conn, msg_type=REQUEST, payload=payload)
        msg_type, payload = _recv_peer_msg(peer_conn)

        if msg_type != 7:
            logging.error(f"{msg_type=} is not 7 (PIECE)")

        recv_piece_idx = int.from_bytes(payload[:4], byteorder='big')
        recvd_piece_offset = int.from_bytes(payload[4:8], byteorder='big')
        logging.info(f"recvd piece idx: {recv_piece_idx}")
        logging.info(f"recvd piece offset: {recvd_piece_offset}")
        assert recv_piece_idx == query_piece_index
        assert recvd_piece_offset == block_offset
        actual_recvd_data_len = len(payload[8:])
        logging.info(f"{actual_recvd_data_len=}")
        piece += payload[8:]
        assert actual_recvd_data_len == block_len_to_downld
        block_offset += block_len_to_downld
    return piece


def _recv_exact_bytes(client_socket, num_bytes):
    """
    Receive exactly num_bytes from the socket.
    This handles the case where recv() returns fewer bytes than requested.
    """
    data = b''
    while len(data) < num_bytes:
        chunk = client_socket.recv(num_bytes - len(data))
        if not chunk:
            raise ConnectionError("Connection closed while receiving data")
        data += chunk
    return data


def _recv_peer_msg(client_socket):
    """
    This is a blocking call to receive peer message from the peer.
    Peer messages consist of a message length prefix (4 bytes),
    message id (1 byte) and a payload (variable size).

    Returns: (msg_type, payload) or (None, b'') for keep-alive
    """
    try:
        # Receive exactly 4 bytes for message length prefix
        length_bytes = _recv_exact_bytes(client_socket, 4)
        msg_len = int.from_bytes(length_bytes, byteorder='big')

        logging.info(f"Received message length: {msg_len}")

        # Handle keep-alive message (length 0)
        if msg_len == 0:
            logging.info("Received keep-alive message")
            return None, b''

        # Receive exactly msg_len bytes for the message body
        message_body = _recv_exact_bytes(client_socket, msg_len)

        # Extract message type (first byte) and payload (rest)
        msg_type = message_body[0]  # This is already an int in Python 3
        payload = message_body[1:]

        logging.info(f"Received message: type={msg_type}, payload_length={len(payload)}")

        # Validate message type
        if msg_type > 8:
            logging.error(f"Invalid message type: {msg_type}. This indicates a parsing error!")
            logging.error(f"Message body (first 20 bytes): {message_body[:20].hex()}")
            raise ValueError(f"Invalid message type: {msg_type}")

        return msg_type, payload

    except Exception as e:
        logging.error(f"Error receiving message: {e}")
        raise


# def _recv_peer_msg(client_socket):
#     """
#     This is a blocking call to receive peer message from the peer.
#     Peer messages consist of a message length prefix (4 bytes),
#     message id (1 byte) and a payload (variable size).
#
#     message length excludes the 4 bytes of the prefix used to store message length.
#     """
#     # Due to TCP chunking, we must always use recv() with the exact number of bytes that we want.
#     # Expected Message length is different from the chunk length the peer sends,
#     # this is because it is possible the peer was able to send only partial payload at a time, say 1KB at a time over TCP
#     # But the expected payload length in the message is 16KB. So we need to loop over recv(n) until we are able to
#     # read entire msg.
#     data_prefix = client_socket.recv(4)
#     msg_len = int.from_bytes(data_prefix, byteorder='big')
#     logging.info(f"received {msg_len=}")
#     data = b''
#     while msg_len > 0:
#         chunk = client_socket.recv(msg_len)
#         data += chunk
#         msg_len -= len(chunk)
#     msg_type = int.from_bytes(data[:1], byteorder='big')
#     payload = data[1:]
#     return msg_type, payload

def _send_peer_msg(client_socket, *, msg_type: int, payload: bytes):
    """


    :param client_socket:
    :param msg_type:
    :param payload: payload to send.
    :return:
    """
    # msg_len = 1 byte for the msg_type and len(payload). The 4 bytes used for the msg_len itself are excluded.
    msg_len = 1 + len(payload)
    msg = msg_len.to_bytes(length=4, byteorder='big') + msg_type.to_bytes(length=1, byteorder='big') + payload
    client_socket.sendall(msg)


def _tor_protocol_handshake_with_peer(client_socket, sha_hash_as_bytes):
    """
    The handshake is a message consisting of the following parts as described in the peer protocol:

    -length of the protocol string (BitTorrent protocol) which is 19 (1 byte)
    -the string BitTorrent protocol (19 bytes)
    -eight reserved bytes, which are all set to zero (8 bytes)
    -sha1 infohash (20 bytes) (NOT the hexadecimal representation, which is 40 bytes long)
    -peer id (20 bytes) (generate 20 random byte values)
    """
    # Send a message after handshake
    len_protocol_str = 19
    message = len_protocol_str.to_bytes(1, byteorder='big')
    message += b'BitTorrent protocol'
    my_zero = 0
    # 8 empty bytes
    message += my_zero.to_bytes(8)
    message += sha_hash_as_bytes
    message += _get_peer_id(as_bytes=True)
    client_socket.sendall(message)
    # Receive a response similar to the above from peer.
    peer_handshake_data = client_socket.recv(1024)
    # last 20 bytes of the peer_handshake_data represents the peer id.
    server_peer_id = peer_handshake_data[-20:]
    # Print the server peer id as hexadecimal.
    print(f"Handshake successful. Peer ID: {server_peer_id.hex()}")


if __name__ == "__main__":
    main()
