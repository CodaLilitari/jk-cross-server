#!/usr/bin/env python3
"""Compile actual GNSServer methods with inert, bounded transport fixtures."""
import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--cxx", default="c++")
    args = parser.parse_args()
    source = args.source.resolve()
    text = (source / "src/Platform/Networking/GNS/stdComm_GNS.cpp").read_text()
    # GNSServer and GNSClient have similarly named methods. Restrict extraction
    # to the production server class; copy each body verbatim, never replace it.
    server = text[text.index("class GNSServer"):text.index("class GNSClient")]
    definitions = {
        "Client": "    struct Client_t\n",
        "Receive": "    int Receive(int *pIdOut, void *pMsg, int *pLenInOut)\n",
        "Send": "    int Send(uint32_t idFrom, uint32_t idTo, void *lpData, uint32_t dwDataSize)\n",
        "SendBytesToAllClients": "    void SendBytesToAllClients( void *pData, uint32_t len, HSteamNetConnection except = k_HSteamNetConnection_Invalid )\n",
        "RetireNativeConnection": "    bool RetireNativeConnection(HSteamNetConnection connection)\n",
    }
    with tempfile.TemporaryDirectory(prefix="jk-native-probe-") as directory:
        temporary = Path(directory)
        for name, signature in definitions.items():
            start = server.index(signature)
            closing = "\n    };" if name == "Client" else "\n    }"
            end = server.index(closing, start) + len(closing)
            (temporary / f"probe_{name}.inc").write_text(server[start:end] + "\n")
        binary = temporary / "test_native_probe_traffic"
        subprocess.run([args.cxx, "-std=c++17", "-O2", "-UNDEBUG", "-Wall", "-Wextra",
                        "-Werror", "-Wno-sign-compare", "-pedantic", "-I", str(source / "src"),
                        "-I", str(temporary), str(Path(__file__).with_name("test_native_probe_traffic.cpp")),
                        "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
