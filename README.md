[![progress-banner](https://backend.codecrafters.io/progress/bittorrent/aa7a1bf4-b506-48a9-abee-524636f91ccb)](https://app.codecrafters.io/users/codecrafters-bot?r=2qF)

This is a starting point for Python solutions to the
["Build Your Own BitTorrent" Challenge](https://app.codecrafters.io/courses/bittorrent/overview).

In this challenge, you’ll build a BitTorrent client that's capable of parsing a
.torrent file and downloading a file from a peer. Along the way, we’ll learn
about how torrent files are structured, HTTP trackers, BitTorrent’s Peer
Protocol, pipelining and more.

**Note**: If you're viewing this repo on GitHub, head over to
[codecrafters.io](https://codecrafters.io) to try the challenge.

# Passing the first stage

The entry point for your BitTorrent implementation is in `app/main.py`. Study
and uncomment the relevant code, and push your changes to pass the first stage:

```sh
git commit -am "pass 1st stage" # any msg
git push origin master
```

Time to move on to the next stage!

# Stage 2 & beyond

Note: This section is for stages 2 and beyond.

1. Ensure you have `python (3.11)` installed locally
1. Run `./your_bittorrent.sh` to run your program, which is implemented in
   `app/main.py`.
1. Commit your changes and run `git push origin master` to submit your solution
   to CodeCrafters. Test output will be streamed to your terminal.


########################################################################################################

## Supported commands:
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


### Bencoding data:

- dict: Encoded as 'd<key><value>...e' with keys sorted lexicographically.
- list: Encoded as 'l<item>...e'.
- str: Encoded as '<length>:<string>' (UTF-8 bytes).
- int: Encoded as 'i<integer>e'.
- bytes: Encoded as '<length>:<bytes>' (raw bytes, not decoded).