"""The default test run must be offline."""

from __future__ import annotations

import socket

import pytest
from pytest_socket import SocketBlockedError


@pytest.mark.filterwarnings("ignore:A test tried to use socket.socket")
def test_network_sockets_are_blocked() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
