"""WebSocket proxy handler method."""

import logging
import select
import socket
import ssl

from src.api import config

logger = logging.getLogger(__name__)


class WebSocketMixin:

    def handle_websocket_proxy(self):
        """Proxy WebSocket upgrade to Mosquitto's WebSocket listener on port 9001."""
        try:
            backend = socket.create_connection(
                (config.MOSQUITTO_WS_HOST, config.MOSQUITTO_WS_PORT),
                timeout=5)
        except (socket.error, OSError) as e:
            logger.error(
                "[WEBSOCKET] Cannot connect to Mosquitto WS (port %s): %s",
                config.MOSQUITTO_WS_PORT, e)
            self.send_error(502, "MQTT broker WebSocket unavailable")
            return

        # Reconstruct the HTTP upgrade request for Mosquitto
        request = "GET / HTTP/1.1\r\n"
        for key, value in self.headers.items():
            if key.lower() == "host":
                request += (f"Host: {config.MOSQUITTO_WS_HOST}:"
                            f"{config.MOSQUITTO_WS_PORT}\r\n")
            else:
                request += f"{key}: {value}\r\n"
        request += "\r\n"
        backend.sendall(request.encode())

        # Take over the raw socket for bidirectional relay
        client = self.connection
        self.close_connection = True
        logger.info(
            "[WEBSOCKET] Proxying to Mosquitto WS (port %s)",
            config.MOSQUITTO_WS_PORT)

        try:
            while True:
                readable, _, _ = select.select(
                    [client, backend], [], [], 120)
                if not readable:
                    break  # timeout - no traffic in either direction
                for sock in readable:
                    other = backend if sock is client else client
                    try:
                        data = sock.recv(8192)
                    except ssl.SSLWantReadError:
                        continue
                    except (ssl.SSLError, OSError):
                        data = b""
                    if not data:
                        return
                    other.sendall(data)
                    # Drain any data buffered in the SSL layer
                    while hasattr(sock, "pending") and sock.pending() > 0:
                        other.sendall(sock.recv(sock.pending()))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            backend.close()
            logger.info("[WEBSOCKET] Connection closed")
