"""
Chromecast Caster Module

Automatic casting to Chromecast devices using PyChromecast.
No browser or user interaction required.

Usage:
    from chromecast_caster import ChromecastCaster

    caster = ChromecastCaster(app_id="76719249")
    caster.connect("192.168.5.187")
    caster.cast_url("http://192.168.4.217:8080/lyrics?song=123")
    caster.disconnect()
"""

import pychromecast
import pychromecast.controllers
import time
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class CustomMessageController(pychromecast.controllers.BaseController):
    """Controller for sending custom messages to the receiver."""

    def __init__(self, namespace: str):
        super().__init__(namespace, "CC")
        self.namespace = namespace

    def receive_message(self, _message, data):
        logger.debug(f"Received from receiver: {data}")
        return True

    def send(self, data: dict):
        """Send a message to the receiver."""
        self.send_message(data)


class ChromecastCaster:
    """
    Manages Chromecast connections and casting operations.

    Args:
        app_id: Google Cast Application ID from Cast Developer Console
        namespace: Custom message namespace (must match receiver)
    """

    def __init__(
        self,
        app_id: str,
        namespace: str = "urn:x-cast:com.casttest.custom"
    ):
        self.app_id = app_id
        self.namespace = namespace
        self.cast: Optional[pychromecast.Chromecast] = None
        self.controller: Optional[CustomMessageController] = None
        self._browser = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to a Chromecast."""
        return self.cast is not None

    @property
    def device_name(self) -> Optional[str]:
        """Get the connected device's friendly name."""
        return self.cast.name if self.cast else None

    def connect(self, ip: str, timeout: float = 10.0) -> bool:
        """
        Connect to a Chromecast by IP address.

        Args:
            ip: IP address of the Chromecast
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        try:
            logger.info(f"Connecting to Chromecast at {ip}...")

            chromecasts, browser = pychromecast.get_chromecasts(
                known_hosts=[ip],
                timeout=timeout
            )
            self._browser = browser

            if not chromecasts:
                logger.error(f"No Chromecast found at {ip}")
                pychromecast.discovery.stop_discovery(browser)
                return False

            self.cast = chromecasts[0]
            self.cast.wait(timeout=timeout)

            # Create and register the message controller
            self.controller = CustomMessageController(self.namespace)
            self.cast.register_handler(self.controller)

            logger.info(f"Connected to: {self.cast.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from the Chromecast."""
        if self._browser:
            pychromecast.discovery.stop_discovery(self._browser)
            self._browser = None

        if self.cast:
            try:
                self.cast.quit_app()
            except:
                pass
            self.cast = None
            self.controller = None

        logger.info("Disconnected")

    def launch_receiver(self, timeout: float = 10.0) -> bool:
        """
        Launch the custom receiver app on the Chromecast.

        Args:
            timeout: Time to wait for app to launch

        Returns:
            True if app launched successfully
        """
        if not self.cast:
            logger.error("Not connected to Chromecast")
            return False

        logger.info(f"Launching receiver app {self.app_id}...")
        self.cast.start_app(self.app_id)

        # Wait for app to launch
        start = time.time()
        while time.time() - start < timeout:
            if self.cast.app_id == self.app_id:
                logger.info("Receiver app launched successfully")
                return True
            time.sleep(0.5)

        logger.warning(f"App may not have launched. Current app: {self.cast.app_id}")
        return False

    def _send_message(self, data: dict) -> bool:
        """Send a message to the receiver."""
        if not self.controller:
            logger.error("No controller - not connected or app not launched")
            return False

        try:
            self.controller.send(data)
            logger.debug(f"Sent message: {data}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def cast_url(self, url: str) -> bool:
        """
        Cast a URL to display on the Chromecast.

        The receiver will load this URL in an iframe.
        URL must be accessible from the Chromecast's network.

        Args:
            url: URL to display (use LAN IP, not localhost)

        Returns:
            True if message sent successfully
        """
        logger.info(f"Casting URL: {url}")
        return self._send_message({"loadUrl": url})

    def clear_content(self) -> bool:
        """Clear the displayed content and show standby screen."""
        logger.info("Clearing content")
        return self._send_message({"clearUrl": True})

    def send_message(self, message: str) -> bool:
        """Display a text message on the receiver."""
        return self._send_message({"message": message})

    def set_background(self, css_background: str) -> bool:
        """Change the receiver's background (CSS value)."""
        return self._send_message({"background": css_background})


# Convenience functions for simple usage

def cast_to_device(
    device_ip: str,
    url: str,
    app_id: str = "76719249",
    namespace: str = "urn:x-cast:com.casttest.custom"
) -> bool:
    """
    One-shot function to cast a URL to a Chromecast.

    Args:
        device_ip: IP address of the Chromecast
        url: URL to display
        app_id: Cast Application ID
        namespace: Message namespace

    Returns:
        True if successful
    """
    caster = ChromecastCaster(app_id, namespace)

    if not caster.connect(device_ip):
        return False

    if not caster.launch_receiver():
        caster.disconnect()
        return False

    # Give receiver a moment to initialize
    time.sleep(1)

    success = caster.cast_url(url)

    # Don't disconnect - keep session alive for future updates
    # caster.disconnect()

    return success


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test casting
    success = cast_to_device(
        device_ip="192.168.5.187",
        url="http://192.168.4.217:8080/receiver.html",
        app_id="76719249"
    )

    if success:
        print("\n✓ Cast successful!")
    else:
        print("\n✗ Cast failed")
