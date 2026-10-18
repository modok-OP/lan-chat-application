import socket
from typing import List


def get_lan_ips() -> List[str]:
    """Discover reachable non-loopback local IPv4 addresses on the host system."""
    ips = set()

    # Discover outbound interface IP via UDP routing table lookup
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        primary = s.getsockname()[0]
        s.close()
        if primary and not primary.startswith("127."):
            ips.add(primary)
    except Exception:
        pass

    # Discover additional adapter IPs associated with local hostname
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    return sorted(list(ips))
