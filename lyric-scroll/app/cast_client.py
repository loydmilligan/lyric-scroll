"""Direct Chromecast control using pychromecast."""

import logging
from typing import Optional
import pychromecast
from pychromecast.controllers.dashcast import DashCastController

logger = logging.getLogger(__name__)

# Cache of connected chromecasts by IP
_chromecasts: dict = {}


def get_chromecast_by_ip(ip_address: str) -> Optional[pychromecast.Chromecast]:
    """Get or create a Chromecast connection by IP address."""
    if ip_address in _chromecasts:
        cc = _chromecasts[ip_address]
        # Check if still connected
        if cc.socket_client and cc.socket_client.is_connected:
            return cc

    try:
        logger.info(f"Connecting to Chromecast at {ip_address}...")
        # Connect directly by IP (no discovery needed)
        chromecasts, browser = pychromecast.get_listed_chromecasts(
            friendly_names=None,
            uuids=None,
            hosts=[ip_address]
        )

        if chromecasts:
            cc = chromecasts[0]
            cc.wait()
            _chromecasts[ip_address] = cc
            logger.info(f"Connected to Chromecast: {cc.cast_info.friendly_name}")
            return cc
        else:
            logger.error(f"No Chromecast found at {ip_address}")
            return None

    except Exception as e:
        logger.error(f"Error connecting to Chromecast at {ip_address}: {e}")
        return None


def cast_url_to_ip(ip_address: str, url: str, force_launch: bool = True) -> bool:
    """Cast a URL to a Chromecast using DashCast.

    Args:
        ip_address: The Chromecast's IP address
        url: The URL to cast
        force_launch: Whether to force launch even if something is playing

    Returns:
        True if successful, False otherwise
    """
    try:
        cc = get_chromecast_by_ip(ip_address)
        if not cc:
            return False

        # Use DashCast to display URL
        dashcast = DashCastController()
        cc.register_handler(dashcast)

        # Load the URL
        logger.info(f"Casting {url} to {cc.cast_info.friendly_name} via DashCast")
        dashcast.load_url(url, force=force_launch)
        return True

    except Exception as e:
        logger.error(f"Cast error: {e}")
        return False


def disconnect_all():
    """Disconnect all cached Chromecast connections."""
    for ip, cc in _chromecasts.items():
        try:
            cc.disconnect()
        except:
            pass
    _chromecasts.clear()
