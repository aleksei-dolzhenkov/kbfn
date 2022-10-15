import asyncio
import logging

from evdev import InputEvent, KeyEvent, ecodes

from base import ModLayer
from helpers import convert_keycode_map


MOD_THRESHOLD = 0.5
FIRST_KEY_DELAY = 0.05

_logger = logging.getLogger(__name__)


class DualRoleSwitchLayer(ModLayer):
    _keycodes: dict = None

    is_fn_active: bool = False
    is_fn_used: bool = False
    fn_activate_time: float

    pressed_keys = set()
    release_key_codes = {}

    first_fn_event: InputEvent = None
    first_fn_event_passed: bool = False

    def configure(self, codes=None):
        self._keycodes = convert_keycode_map(codes or {})

    def activate_fn_layer(self, event: InputEvent):
        self.is_fn_active = True

        self.is_fn_used = False
        self.fn_activate_time = event.timestamp()
        self.first_fn_event = None
        self.first_fn_event_passed: bool = False

    def deactivate_fn_layer(self):
        self.is_fn_active = False

    def update_pressed_keys(self, event: InputEvent):
        if event.value == KeyEvent.key_down:
            self.pressed_keys.add(event.code)

        elif event.value == KeyEvent.key_up and event.code in self.pressed_keys:
            self.pressed_keys.remove(event.code)

    def _write_event(self, event: InputEvent):
        if event.type == ecodes.EV_KEY:
            self.update_pressed_keys(event)

            key_state = ('up', 'down', 'hold')[event.value]
            key = ecodes.keys.get(event.code)
            _logger.debug('write event:\t%s\t%s', key, key_state)

        self.out.send(event)

    def _write_space(self, key_down_event: InputEvent):
        self._write_event(InputEvent(
            key_down_event.sec,
            key_down_event.usec,
            ecodes.EV_KEY,
            ecodes.KEY_SPACE,
            KeyEvent.key_down
        ))
        self._write_event(key_down_event)

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

            if key_code == ecodes.KEY_SPACE:
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

                if key_code not in self._keycodes:
                    return

                event.code = self._keycodes[key_code]

                if event.value == KeyEvent.key_down:
                    self.release_key_codes[key_code] = event.code
                    self.is_fn_used = True
                elif event.value == KeyEvent.key_up:
                    self.release_key_codes.pop(key_code, None)

        self._write_event(event)

    def send(self, event: InputEvent):
        if event.type == ecodes.EV_KEY and event.code == ecodes.KEY_SPACE:
            if event.value == KeyEvent.key_down and not self.is_fn_active:
                self.activate_fn_layer(event)

            elif event.value == KeyEvent.key_up:
                self.deactivate_fn_layer()
                if not self.is_fn_used and event.timestamp() - self.fn_activate_time < MOD_THRESHOLD:
                    self._write_space(event)

                    if self.first_fn_event and not self.first_fn_event_passed:
                        if (event.timestamp() - self.first_fn_event.timestamp()) < FIRST_KEY_DELAY:
                            self._write_event(self.first_fn_event)

        elif event.type == ecodes.EV_KEY and self.is_fn_active:
            self._handle_fn_event(event)
        elif event.type == ecodes.EV_KEY and event.value in (KeyEvent.key_up, KeyEvent.key_hold):
            # modify `event.code` if fn-layer key was released after FN layer deactivated
            event.code = self.release_key_codes.pop(event.code, event.code)

            if event.code not in self.pressed_keys:
                return

            self._write_event(event)
        else:
            self._write_event(event)
