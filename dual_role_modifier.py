import asyncio
import logging
from typing import Optional

from evdev import InputEvent, KeyEvent, ecodes

from base import AbstractLayer, ModLayer


MOD_THRESHOLD = 0.5
FIRST_KEY_DELAY = 0.05

_logger = logging.getLogger(__name__)


class DualRoleMod(ModLayer):  # FIXME: separate into 2 classes
    key_code: int
    mod_code: int

    is_fn_active: bool = False
    is_fn_used: bool = False
    fn_activate_time: float

    pressed_keys: set = None
    release_key_codes: dict = None

    # tap interrupting
    first_fn_event: Optional[InputEvent] = None
    first_fn_event_passed: bool = False

    def __init__(self, key_code: int, mod_code: int, out: AbstractLayer):
        super().__init__(out)

        self.pressed_keys = set()
        self.release_key_codes = dict()

        self.key_code = key_code
        self.mod_code = mod_code

    def activate_fn_layer(self, event: InputEvent):
        self.is_fn_active = True

        self.is_fn_used = False
        self.fn_activate_time = event.timestamp()
        self.first_fn_event = None
        self.first_fn_event_passed: bool = False

    def deactivate_fn_layer(self, event: InputEvent):
        self.is_fn_active = False
        if self.is_fn_used:
            self._write_key_up(self.mod_code, event.sec, event.usec)

    def update_pressed_keys(self, event: InputEvent):
        if event.value == KeyEvent.key_down:
            self.pressed_keys.add(event.code)
        elif event.value == KeyEvent.key_up and event.code in self.pressed_keys:
            self.pressed_keys.remove(event.code)

    def _write_event(self, event: InputEvent):
        if event.type == ecodes.EV_KEY:
            self.update_pressed_keys(event)

            _key_state = ('up', 'down', 'hold')[event.value]
            _key = ecodes.keys.get(event.code)
            _logger.debug('write event:\t%s\t%s', _key, _key_state)

        self.out.send(event)

    def _write_key_up(self, key_code, sec, usec):
        self._write_event(InputEvent(sec, usec, ecodes.EV_KEY, key_code, KeyEvent.key_up))

    def _write_key_down(self, key_code, sec, usec):
        self._write_event(InputEvent(sec, usec, ecodes.EV_KEY, key_code, KeyEvent.key_down))

    def _write_key_down_before_up(self, key_up_event: InputEvent):
        self._write_event(InputEvent(
            key_up_event.sec,
            key_up_event.usec,
            ecodes.EV_KEY,
            self.key_code,
            KeyEvent.key_down
        ))
        self._write_event(key_up_event)

    async def _first_fn_key_press(self):
        await asyncio.sleep(FIRST_KEY_DELAY)

        _logger.debug('CALLBACK')
        if not self.is_fn_active:
            return

        if not self.first_fn_event_passed:
            self.first_fn_event_passed = True
            self._handle_fn_event(self.first_fn_event)

    def _handle_fn_event(self, event: InputEvent):
        if event.type == ecodes.EV_KEY:
            key_code = event.code

            if key_code == self.key_code:
                return

            # pass the event unmodified if the key was pressed before FN layer activated
            if key_code not in self.pressed_keys:
                if not self.first_fn_event:
                    self.first_fn_event = event
                    asyncio.create_task(self._first_fn_key_press())
                    return

                if not self.first_fn_event_passed:
                    self.first_fn_event_passed = True
                    self._handle_fn_event(self.first_fn_event)

                if not self.is_fn_used:
                    self.is_fn_used = True
                    self._write_key_down(self.mod_code, event.sec, event.usec)

        self._write_event(event)

    def send(self, event: InputEvent):
        if event.type == ecodes.EV_KEY and event.code == self.key_code:
            if event.value == KeyEvent.key_down and not self.is_fn_active:
                self.activate_fn_layer(event)

            elif event.value == KeyEvent.key_up:
                self.deactivate_fn_layer(event)
                if not self.is_fn_used and event.timestamp() - self.fn_activate_time < MOD_THRESHOLD:
                    self._write_key_down_before_up(event)

                    if self.first_fn_event and not self.first_fn_event_passed:
                        if (event.timestamp() - self.first_fn_event.timestamp()) < FIRST_KEY_DELAY:
                            self._write_event(self.first_fn_event)

        elif event.type == ecodes.EV_KEY and self.is_fn_active:
            self._handle_fn_event(event)
        else:
            self._write_event(event)
