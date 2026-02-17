# motion.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import serial
from serial.tools import list_ports


DONE_TOKEN = "DONE"


@dataclass
class MotionConfig:
    port: Optional[str] = None
    baud: int = 115200
    connect_reset_delay_s: float = 2.0   # Arduino often resets on serial open
    read_timeout_s: float = 0.05         # serial read timeout
    write_timeout_s: float = 0.2
    done_token: str = DONE_TOKEN


class MotionController:
    """
    Arduino motion controller wrapper.

    Protocol (Arduino side):
      - 'H\\n' hold/enable
      - 'R\\n' release/disable
      - 'Z\\n' zero (set current position to 0)
      - 'M<deg>\\n' move to absolute output angle in degrees
      - Arduino prints 'DONE\\n' when motion completes
    """

    def __init__(self, cfg: MotionConfig):
        self.cfg = cfg
        self._ser: Optional[serial.Serial] = None
        self._rx_buf = bytearray()

    # --------- lifecycle ---------
    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def connect(self) -> None:
        if self.is_connected:
            return

        # Auto-detect port instead of using fixed COM
        if not self.cfg.port:
            self.cfg.port = self.find_esp_port()

        self._ser = serial.Serial(
            port=self.cfg.port,
            baudrate=self.cfg.baud,
            timeout=self.cfg.read_timeout_s,
            write_timeout=self.cfg.write_timeout_s,
        )

        # Give Arduino time to reboot on serial open (common on Uno/Nano/Mega)
        if self.cfg.connect_reset_delay_s > 0:
            time.sleep(self.cfg.connect_reset_delay_s)

        self.drain()
        
        # Automatically release motor on connection
        self.release()

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None
                self._rx_buf.clear()

    def __enter__(self) -> "MotionController":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # --------- io helpers ---------
    def drain(self) -> None:
        """Clear any pending input so old DONEs don't confuse us."""
        if not self.is_connected:
            return
        try:
            self._ser.reset_input_buffer()
        except Exception:
            # Fallback: read whatever is there
            try:
                while self._ser.in_waiting:
                    self._ser.read(self._ser.in_waiting)
            except Exception:
                pass
        self._rx_buf.clear()

    def _write_ascii(self, s: str) -> None:
        if not self.is_connected:
            raise RuntimeError("MotionController not connected.")
        self._ser.write(s.encode("ascii"))

    def _read_lines_nonblocking(self) -> list[str]:
        """
        Reads available bytes and returns any complete lines (\\n-terminated)
        decoded as strings without trailing whitespace.
        """
        if not self.is_connected:
            return []

        chunk = self._ser.read(128)
        if not chunk:
            return []

        self._rx_buf.extend(chunk)
        lines: list[str] = []

        while True:
            nl = self._rx_buf.find(b"\n")
            if nl < 0:
                break
            raw = self._rx_buf[:nl]
            del self._rx_buf[: nl + 1]

            # strip CR/spaces
            txt = raw.decode(errors="ignore").strip()
            if txt:
                lines.append(txt)

        return lines

    def find_esp_port(self) -> str:
        TARGET_VID = 0x1A86
        TARGET_PID = 0x55D4

        for port in list_ports.comports():
            if port.vid == TARGET_VID and port.pid == TARGET_PID:
                return port.device

        raise RuntimeError("ESP32 (CH340) not found")

    # --------- commands ---------
    def hold(self) -> None:
        self._write_ascii("H\n")

    def release(self) -> None:
        self._write_ascii("R\n")

    def zero(self) -> None:
        self._write_ascii("Z\n")

    def move_abs(self, deg: float) -> None:
        """
        Move to absolute output angle in degrees.
        deg can be float, negative allowed.
        """
        # Keep formatting simple + stable for Arduino atof():
        # no commas, no scientific notation
        cmd = f"M{deg:.6f}\n"
        self._write_ascii(cmd)

    def wait_done(self, timeout_s: float = 10.0, *, stop_flag=None) -> bool:
        """
        Wait for DONE token.
        Returns True if received; False on timeout or stop_flag set.

        stop_flag: optional threading.Event-like object with is_set()
        """
        if not self.is_connected:
            raise RuntimeError("MotionController not connected.")

        deadline = time.time() + float(timeout_s)
        done_token = self.cfg.done_token

        while time.time() < deadline:
            if stop_flag is not None and stop_flag.is_set():
                return False

            for line in self._read_lines_nonblocking():
                if line == done_token:
                    return True

            time.sleep(0.001)

        return False
