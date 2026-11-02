import io
import ipaddress
import socket

import psutil
import segno
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.schemas import ConnectOut

router = APIRouter(prefix="/api/connect")


_PHYSICAL_INTERFACE_PREFIXES = ("en", "eth", "wl")


def _is_lan_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.version == 4 and ip.is_private and not ip.is_loopback and not ip.is_link_local


def pick_lan_address(route_address: str | None, interfaces: dict[str, list[str]]) -> str | None:
    """Choose the address a phone on the same Wi-Fi can reach.

    Private addresses on Wi-Fi or Ethernet interfaces win over VPN tunnels and virtual-machine
    bridges; among those, the one the system routes through is preferred.
    """
    candidates = sorted(
        (not name.startswith(_PHYSICAL_INTERFACE_PREFIXES), address != route_address, name, address)
        for name, addresses in interfaces.items()
        for address in addresses
        if _is_lan_address(address)
    )
    return candidates[0][-1] if candidates else None


def _default_route_address() -> str | None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            # Connecting a UDP socket sends nothing; it only picks the outgoing interface.
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
        except OSError:
            return None


def lan_address() -> str | None:
    stats = psutil.net_if_stats()
    interfaces = {
        name: [address.address for address in addresses if address.family == socket.AF_INET]
        for name, addresses in psutil.net_if_addrs().items()
        if name not in stats or stats[name].isup
    }
    return pick_lan_address(_default_route_address(), interfaces)


def port_open(address: str, port: int) -> bool:
    try:
        with socket.create_connection((address, port), timeout=0.5):
            return True
    except OSError:
        return False


def _request_port(request: Request) -> int:
    return request.url.port or (443 if request.url.scheme == "https" else 80)


def connect_url(request: Request) -> str | None:
    address = lan_address()
    if address is None:
        return None
    return f"{request.url.scheme}://{address}:{_request_port(request)}/"


@router.get("")
def connect_info(request: Request) -> ConnectOut:
    address = lan_address()
    if address is None:
        return ConnectOut(url=None, reachable=False)
    port = _request_port(request)
    return ConnectOut(url=f"{request.url.scheme}://{address}:{port}/", reachable=port_open(address, port))


@router.get("/qr.svg")
def connect_qr(request: Request) -> Response:
    url = connect_url(request)
    if url is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No network address was found for this computer.")
    svg = io.BytesIO()
    segno.make(url, error="m").save(svg, kind="svg", scale=8, border=2, dark="#1c2a21", light="#ffffff")
    return Response(svg.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})
