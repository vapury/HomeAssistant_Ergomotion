import asyncio
import datetime
import logging
import time
from typing import Callable

from bleak import BleakClient, BLEDevice, BleakError
from bleak_retry_connector import establish_connection

_LOGGER = logging.getLogger(__name__)

UUID_NOTIFY = "0000ffe4-0000-1000-8000-00805f9b34fb"
UUID_WRITE = "0000ffe9-0000-1000-8000-00805f9b34fb"


def calc_crc(data: bytes) -> int:
    return (~sum(data)) & 0xFF


def build_command_packet(command: int) -> bytes:
    data = b"\xe5\xfe\x16" + command.to_bytes(4, "little")
    return data + bytes([calc_crc(data)])


def build_time_packet() -> bytes:
    now = datetime.datetime.now()
    data = bytes([
        0xE7,
        0x80,
        0x01,
        (now.year - 1900) & 0xFF,
        (now.month - 1) & 0xFF,
        now.day & 0xFF,
        now.hour & 0xFF,
        now.minute & 0xFF,
        now.second & 0xFF,
    ])
    return data + bytes([calc_crc(data)])


class Client:
    def __init__(self, device: BLEDevice, callback: Callable, hass=None):
        self.device = device
        self.callback = callback
        self.hass = hass

        self.client: BleakClient | None = None
        self._running = True
        self._connect_task: asyncio.Task | None = None
        self._pending_actions: list[Callable] = []

        self.pulse_task: asyncio.Task | None = None

        self.start()

    @property
    def is_connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    def _get_ble_device(self) -> BLEDevice:
        """Get freshest BLEDevice from HA bluetooth manager if available."""
        if self.hass:
            try:
                from homeassistant.components import bluetooth
                freshest = bluetooth.async_ble_device_from_address(
                    self.hass, self.device.address, connectable=True
                )
                if freshest:
                    return freshest
            except Exception as e:
                _LOGGER.debug("Could not get freshest BLEDevice: %s", e)
        return self.device

    def start(self):
        """Start persistent background connection."""
        if not self._connect_task or self._connect_task.done():
            self._connect_task = asyncio.create_task(self._persistent_loop())

    def ping(self):
        """Ensure connection loop is running."""
        self.start()

    async def _persistent_loop(self):
        """Always maintain connection to the bed for instant response."""
        while self._running:
            try:
                target_device = self._get_ble_device()
                _LOGGER.debug("Connecting to Ergomotion (%s)...", target_device.address)

                self.client = await establish_connection(
                    BleakClient, target_device, target_device.address
                )

                _LOGGER.info("Ergomotion connected (always-on mode)")
                self.callback(char=None, data=True)

                # Subscribe to notify
                try:
                    await self.client.start_notify(UUID_NOTIFY, self.callback)
                    _LOGGER.debug("Notify registered on %s", UUID_NOTIFY)
                except Exception as ex:
                    _LOGGER.warning("Could not register notify on %s: %s", UUID_NOTIFY, ex)

                # Send initTime sync packet
                await asyncio.sleep(1.0)
                try:
                    time_pkt = build_time_packet()
                    await self._write_to_char(time_pkt)
                except Exception:
                    pass

                # Execute any commands queued while reconnecting
                while self._pending_actions and self.client and self.client.is_connected:
                    action = self._pending_actions.pop(0)
                    try:
                        await action()
                    except Exception as ex:
                        _LOGGER.warning("Error executing queued action: %s", ex)

                # Keep-alive loop while connection holds
                while self._running and self.client and self.client.is_connected:
                    await asyncio.sleep(2.0)

            except TimeoutError:
                _LOGGER.debug("BLE connection timeout, retrying in 3s...")
            except BleakError as e:
                _LOGGER.debug("BLE connection error: %s", e)
            except Exception as e:
                _LOGGER.warning("Connection error: %s", e)
            finally:
                if self.pulse_task and not self.pulse_task.done():
                    self.pulse_task.cancel()
                self.client = None
                self.callback(None, False)
                await asyncio.sleep(3.0)

    async def _write_to_char(self, data: bytes):
        """Write bytes to UUID_WRITE with proper response mode."""
        if not self.client or not self.client.is_connected:
            raise BleakError("Client is not connected")

        use_response = True
        try:
            if self.client.services:
                char = self.client.services.get_characteristic(UUID_WRITE)
                if char and "write-without-response" in char.properties and "write" not in char.properties:
                    use_response = False
        except Exception:
            pass

        await self.client.write_gatt_char(UUID_WRITE, data, response=use_response)

    def send_single(self, command: int):
        """Send command immediately, or queue if reconnecting."""
        self.stop_pulse()
        if self.client and self.client.is_connected:
            asyncio.create_task(self._send_single_coro(command))
        else:
            _LOGGER.info("Bed reconnecting: command 0x%08X queued", command)
            self._pending_actions.append(lambda: self._send_single_coro(command))
            self.ping()

    async def _send_single_coro(self, command: int):
        try:
            packet = build_command_packet(command)
            await self._write_to_char(packet)
            _LOGGER.debug("Sent command: 0x%08X", command)
        except Exception as e:
            _LOGGER.warning("send_single error: %s", e)

    def pulse_command(self, command: int, count: int = 15, interval: float = 0.1):
        """Pulse command immediately, or queue if reconnecting."""
        self.stop_pulse()
        if self.client and self.client.is_connected:
            self.pulse_task = asyncio.create_task(self._pulse_coro(command, count, interval))
        else:
            _LOGGER.info("Bed reconnecting: pulse command 0x%08X queued", command)
            self._pending_actions.append(lambda: self._pulse_coro(command, count, interval))
            self.ping()

    async def _pulse_coro(self, command: int, count: int, interval: float):
        packet = build_command_packet(command)
        stop_pkt = build_command_packet(0)
        try:
            for _ in range(count):
                if not self.client or not self.client.is_connected:
                    break
                await self._write_to_char(packet)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                if self.client and self.client.is_connected:
                    await self._write_to_char(stop_pkt)
            except Exception:
                pass

    def stop_pulse(self):
        self._pending_actions.clear()
        if self.pulse_task and not self.pulse_task.done():
            self.pulse_task.cancel()
        if self.client and self.client.is_connected:
            asyncio.create_task(self._send_stop())

    async def _send_stop(self):
        try:
            await self._write_to_char(build_command_packet(0))
        except Exception:
            pass
