import asyncio
import logging
import time
from typing import TypedDict, Callable

from bleak import BLEDevice, BleakGATTCharacteristic

from .client import Client, build_command_packet

_LOGGER = logging.getLogger(__name__)

CMD_STOP = 0x00000000
CMD_HEAD_UP = 0x00000001
CMD_HEAD_DOWN = 0x00000002
CMD_FOOT_UP = 0x00000004
CMD_FOOT_DOWN = 0x00000008
CMD_ZERO_G = 0x00001000
CMD_LOUNGE = 0x00002000
CMD_LIGHT = 0x00020000
CMD_FLAT = 0x08000000


class Attribute(TypedDict, total=False):
    is_on: bool
    position: int
    move: bool
    value: int | str
    extra: dict


class Device:
    def __init__(self, name: str, device: BLEDevice | None, hass=None):
        self.name = name
        self.hass = hass
        self.client = Client(device, self.on_data, hass=hass) if device else None

        self.connected = False
        self.current_data = None

        self.max_positions = {
            "head": None,
            "foot": None,
        }
        self.calibrated = {
            "head": False,
            "foot": False,
        }

        self.current_preset = "Flat"
        self.preset1_head = 50
        self.preset1_foot = 30
        self.preset2_head = 30
        self.preset2_foot = 15
        self.preset3_head = 70
        self.preset3_foot = 40

        self.current_state = {
            "head_position_raw": 0,
            "foot_position_raw": 0,
            "head_position": 0,
            "foot_position": 0,
            "head_move": False,
            "foot_move": False,
            "led": False,
        }

        self.updates_connect: list[Callable] = []
        self.updates_state: list[Callable] = []

        self._move_task: asyncio.Task | None = None

    @property
    def mac(self) -> str:
        return self.client.device.address if self.client else ""

    def set_max_position(self, motor: str, max_pos: int):
        """Restore or set calibrated max position."""
        if max_pos and max_pos > 0:
            if not self.max_positions[motor] or max_pos > self.max_positions[motor]:
                self.max_positions[motor] = max_pos
                self.calibrated[motor] = True

    def register_update(self, attr: str, handler: Callable):
        if attr == "connection":
            self.updates_connect.append(handler)
        else:
            self.updates_state.append(handler)

    def on_data(self, char: BleakGATTCharacteristic | None, data: bytes | bool):
        if isinstance(data, bool):
            self.connected = data
            for handler in self.updates_connect:
                handler()
            return

        if not isinstance(data, (bytes, bytearray)):
            return

        # Skip duplicate packets to prevent unnecessary HA DB traffic
        if self.current_data == data:
            return

        self.current_data = data
        _LOGGER.debug("BLE status update: %s", data.hex(" "))

        # Validate status packet length (official app accepts only 16, 19, or 20 bytes)
        if len(data) not in (16, 19, 20):
            _LOGGER.debug("Ignoring non-status packet (len=%d): %s", len(data), data.hex(" "))
            return

        # Check CRC: ~sum(data[:-1]) & 0xFF
        expected_crc = (~sum(data[:-1])) & 0xFF
        if data[-1] != expected_crc:
            _LOGGER.debug("BLE packet CRC mismatch: expected %02X, got %02X", expected_crc, data[-1])
            return

        # Parse motor moving flags & LED
        stat_byte = data[14] if len(data) == 19 else data[13]
        self.current_state["led"] = bool(stat_byte & 0x40)
        move = stat_byte & 0x0F
        is_moving_head = bool(move != 0x0F and (move & 1))
        is_moving_foot = bool(move != 0x0F and (move & 2))
        self.current_state["head_move"] = is_moving_head
        self.current_state["foot_move"] = is_moving_foot

        # Parse raw positions
        head_raw = int.from_bytes(data[3:5], "little")
        foot_raw = int.from_bytes(data[5:7], "little")

        # Spike rejection: if bed is not moving and in Flat preset, ignore spurious jumps
        if self.current_preset == "Flat" and not is_moving_head and not is_moving_foot:
            if head_raw > 1500 or foot_raw > 1500:
                _LOGGER.debug(
                    "Spike rejected in Flat state (head_raw=%d, foot_raw=%d)", head_raw, foot_raw
                )
                head_raw = 0
                foot_raw = 0

        # Small residual offset clamp to 0
        if head_raw < 150 and not is_moving_head:
            head_raw = 0
        if foot_raw < 150 and not is_moving_foot:
            foot_raw = 0

        self.current_state["head_position_raw"] = head_raw
        self.current_state["foot_position_raw"] = foot_raw

        # Dynamic calibration: learn peak position only with valid non-spike values
        if head_raw != 0xFFFF and head_raw > 1000:
            if not self.max_positions["head"] or head_raw > self.max_positions["head"]:
                self.max_positions["head"] = head_raw
                self.calibrated["head"] = True
            self.current_state["head_position"] = head_raw
        elif head_raw == 0:
            self.current_state["head_position"] = 0

        if foot_raw != 0xFFFF and foot_raw > 1000:
            if not self.max_positions["foot"] or foot_raw > self.max_positions["foot"]:
                self.max_positions["foot"] = foot_raw
                self.calibrated["foot"] = True
            self.current_state["foot_position"] = foot_raw
        elif foot_raw == 0:
            self.current_state["foot_position"] = 0

        for handler in self.updates_state:
            handler()

    def attribute(self, attr: str) -> Attribute:
        if attr == "connection":
            return Attribute(
                is_on=self.connected,
                extra={"mac": self.mac},
            )

        if attr in ("head_position_raw", "head_position"):
            raw = self.current_state.get("head_position_raw", 0)
            return Attribute(
                position=raw,
                move=self.current_state.get("head_move", False),
            )

        if attr in ("foot_position_raw", "foot_position"):
            raw = self.current_state.get("foot_position_raw", 0)
            return Attribute(
                position=raw,
                move=self.current_state.get("foot_move", False),
            )

        if attr == "preset":
            return Attribute(
                value=self.current_preset,
                extra={
                    "preset1_head": self.preset1_head,
                    "preset1_foot": self.preset1_foot,
                    "preset2_head": self.preset2_head,
                    "preset2_foot": self.preset2_foot,
                    "preset3_head": self.preset3_head,
                    "preset3_foot": self.preset3_foot,
                },
            )

        if attr == "preset1_head":
            return Attribute(value=self.preset1_head)
        if attr == "preset1_foot":
            return Attribute(value=self.preset1_foot)
        if attr == "preset2_head":
            return Attribute(value=self.preset2_head)
        if attr == "preset2_foot":
            return Attribute(value=self.preset2_foot)
        if attr == "preset3_head":
            return Attribute(value=self.preset3_head)
        if attr == "preset3_foot":
            return Attribute(value=self.preset3_foot)

        if attr == "led":
            return Attribute(is_on=self.current_state.get("led", False))

        return Attribute()

    # Commands
    def flat(self):
        self._cancel_move()
        self.current_preset = "Flat"
        self.client.send_single(CMD_FLAT)
        self._notify_state()

    def zerog(self):
        self._cancel_move()
        self.current_preset = "Zero G"
        self.client.send_single(CMD_ZERO_G)
        self._notify_state()

    def lounge(self, duration: float = 2.0):
        self._cancel_move()
        self.current_preset = "Lounge"
        pulses = max(1, int(duration * 10))
        self.client.pulse_command(CMD_LOUNGE, count=pulses)
        self._notify_state()

    def stop(self):
        self._cancel_move()
        self.client.stop_pulse()

    def toggle_light(self):
        self.client.send_single(CMD_LIGHT)

    def select_preset(self, preset: str):
        if preset == "Flat":
            self.flat()
        elif preset == "Zero G":
            self.zerog()
        elif preset == "Lounge":
            self.lounge()
        elif preset in ("Preset 1", "Preset 2", "Preset 3"):
            self.current_preset = preset
            self._notify_state()
            asyncio.create_task(self.move_to_preset(preset))
        elif preset == "Custom":
            self.current_preset = "Custom"
            self._notify_state()

    def set_preset_target(self, preset: str, motor: str, pct: int):
        """Update Preset 1, 2, or 3 target values."""
        if preset == "Preset 1":
            if motor == "head":
                self.preset1_head = pct
            elif motor == "foot":
                self.preset1_foot = pct
        elif preset == "Preset 2":
            if motor == "head":
                self.preset2_head = pct
            elif motor == "foot":
                self.preset2_foot = pct
        elif preset == "Preset 3":
            if motor == "head":
                self.preset3_head = pct
            elif motor == "foot":
                self.preset3_foot = pct

        self._notify_state()

    def manual_cover_moved(self):
        """Called when user manually controls head or foot cover."""
        if self.current_preset != "Custom":
            self.current_preset = "Custom"
            self._notify_state()

    def _notify_state(self):
        for handler in self.updates_state:
            handler()

    async def move_to_preset(self, preset: str):
        """Move head and foot simultaneously to preset target percentages."""
        if preset == "Preset 1":
            target_head = self.preset1_head
            target_foot = self.preset1_foot
        elif preset == "Preset 2":
            target_head = self.preset2_head
            target_foot = self.preset2_foot
        else:
            target_head = self.preset3_head
            target_foot = self.preset3_foot

        head_max = self.max_positions["head"] or 14119
        foot_max = self.max_positions["foot"] or 12959
        target_head_raw = round((target_head / 100.0) * head_max)
        target_foot_raw = round((target_foot / 100.0) * foot_max)

        await self.move_to_targets_simultaneously(target_head_raw, target_foot_raw)

    def _cancel_move(self):
        if self._move_task and not self._move_task.done():
            self._move_task.cancel()
            self._move_task = None

    async def move_to_targets_simultaneously(self, target_head: int, target_foot: int):
        """Move both head and foot motors concurrently."""
        self._cancel_move()
        self._move_task = asyncio.create_task(
            self._simultaneous_move_loop(target_head, target_foot)
        )
        await self._move_task

    async def _simultaneous_move_loop(self, target_head: int, target_foot: int):
        tolerance = 150
        self.client.stop_pulse()
        self.client.ping()

        for _ in range(50):
            if self.client and self.client.is_connected:
                break
            await asyncio.sleep(0.2)

        if not self.client or not self.client.is_connected:
            _LOGGER.warning("Cannot move to target: bed not connected")
            return

        stop_pkt = build_command_packet(0)
        start_time = time.time()

        last_head = self.current_state.get("head_position_raw", 0)
        last_foot = self.current_state.get("foot_position_raw", 0)
        head_stuck_count = 0
        foot_stuck_count = 0

        try:
            while time.time() - start_time < 40.0:
                cur_head = self.current_state.get("head_position_raw", 0)
                cur_foot = self.current_state.get("foot_position_raw", 0)

                # Head direction
                head_cmd = 0
                head_done = False
                if abs(cur_head - target_head) <= tolerance:
                    head_done = True
                elif cur_head < target_head:
                    head_cmd = CMD_HEAD_UP
                else:
                    head_cmd = CMD_HEAD_DOWN

                # Foot direction
                foot_cmd = 0
                foot_done = False
                if abs(cur_foot - target_foot) <= tolerance:
                    foot_done = True
                elif cur_foot < target_foot:
                    foot_cmd = CMD_FOOT_UP
                else:
                    foot_cmd = CMD_FOOT_DOWN

                # Physical limit / stuck detection
                if time.time() - start_time > 1.5:
                    if head_cmd != 0 and abs(cur_head - last_head) < 20:
                        head_stuck_count += 1
                        if head_stuck_count >= 15:
                            head_done = True
                            head_cmd = 0
                    else:
                        head_stuck_count = 0
                        last_head = cur_head

                    if foot_cmd != 0 and abs(cur_foot - last_foot) < 20:
                        foot_stuck_count += 1
                        if foot_stuck_count >= 15:
                            foot_done = True
                            foot_cmd = 0
                    else:
                        foot_stuck_count = 0
                        last_foot = cur_foot

                if head_done and foot_done:
                    break

                if not self.client or not self.client.is_connected:
                    break

                combined_cmd = head_cmd | foot_cmd
                if combined_cmd == 0:
                    break

                pkt = build_command_packet(combined_cmd)
                await self.client._write_to_char(pkt)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                if self.client and self.client.is_connected:
                    await self.client._write_to_char(stop_pkt)
            except Exception:
                pass

    async def move_to_raw_target(self, motor: str, target_raw: int):
        self._cancel_move()
        self._move_task = asyncio.create_task(self._target_move_loop(motor, target_raw))
        await self._move_task

    async def _target_move_loop(self, motor: str, target_raw: int):
        cmds = {
            "head": (CMD_HEAD_UP, CMD_HEAD_DOWN),
            "foot": (CMD_FOOT_UP, CMD_FOOT_DOWN),
        }
        if motor not in cmds:
            return

        cmd_up, cmd_down = cmds[motor]
        key_raw = f"{motor}_position_raw"
        tolerance = 150

        self.client.stop_pulse()
        self.client.ping()

        for _ in range(50):
            if self.client and self.client.is_connected:
                break
            await asyncio.sleep(0.2)

        if not self.client or not self.client.is_connected:
            _LOGGER.warning("Cannot move to target: bed not connected")
            return

        current = self.current_state.get(key_raw, 0)
        if abs(current - target_raw) <= tolerance:
            return

        direction = cmd_up if current < target_raw else cmd_down
        pkt = build_command_packet(direction)
        stop_pkt = build_command_packet(0)

        start_time = time.time()
        last_val = current
        unchanged_count = 0

        try:
            while time.time() - start_time < 35.0:
                current = self.current_state.get(key_raw, 0)
                if direction == cmd_up and current >= (target_raw - tolerance):
                    break
                elif direction == cmd_down and current <= (target_raw + tolerance):
                    break

                # If motor stops changing for 1.5s after starting (reached mechanical limit)
                if time.time() - start_time > 1.5:
                    if abs(current - last_val) < 20:
                        unchanged_count += 1
                        if unchanged_count >= 15:  # ~1.5s
                            _LOGGER.info("Motor %s reached physical limit at raw=%d", motor, current)
                            break
                    else:
                        unchanged_count = 0
                        last_val = current

                if not self.client or not self.client.is_connected:
                    break

                await self.client._write_to_char(pkt)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                if self.client and self.client.is_connected:
                    await self.client._write_to_char(stop_pkt)
            except Exception:
                pass
