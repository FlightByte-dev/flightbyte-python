"""The test suite. It never touches the real API and needs no key.

Every request goes to a server on 127.0.0.1 that the test starts itself. To
make sure of it, connections to any other host fail here, and proxies from
the environment are switched off for the local servers.
"""

import os
import socket

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_create_connection = socket.create_connection


def _local_only(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    host = address[0]
    if host not in _LOCAL_HOSTS:
        raise AssertionError(f"the tests tried to connect to {host}; they must stay on 127.0.0.1")
    return _create_connection(address, *args, **kwargs)


socket.create_connection = _local_only
