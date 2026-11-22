"""Fetch the separately distributed, pinned upstream JKWeb relay for a local run."""
from pathlib import Path
import argparse
import hashlib
import os
import urllib.request

COMMIT = "642afa116f392e5734bad742bfd77c65119a0c52"
SHA256 = "c7d24a708e90ad827952f11c18f1095fdb37ceb95128f0820b76df481da18619"
URL = f"https://raw.githubusercontent.com/tristamus/jkdf2mp-bb-server/{COMMIT}/relay/relay.py"


def fetch(destination):
    destination = Path(destination)
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Existing relay does not match the pinned upstream source; choose another output.")
        return destination
    with urllib.request.urlopen(URL, timeout=30) as response:
        data = response.read(1024 * 1024)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Downloaded relay checksum differs from the verified upstream source.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
        output.write(data)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(fetch(args.destination))
