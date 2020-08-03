import asyncio
import logging
import signal

from typing import Generator, Optional
from asyncio import Future

from evdev import InputDevice, InputEvent, KeyEvent, UInput, ecodes


MOD_THRESHOLD = 0.5
FIRST_KEY_DELAY = 0.05

_logger = logging.getLogger(__name__)


class Shutdown(Exception):
    pass


class State:
    dev_read_future: Optional[Future] = None

    is_fn_active: bool = False
    is_fn_used: bool = False
    fn_activate_time: float

    pressed_keys = set()
    release_key_codes = {}

    first_fn_event: InputEvent = None
    first_fn_event_passed: bool = False

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


state = State()

_keycodes = {
    ecodes.KEY_Z: ecodes.KEY_Z,
    ecodes.KEY_X: ecodes.KEY_X,
    ecodes.KEY_C: ecodes.KEY_C,
    ecodes.KEY_V: ecodes.KEY_V,

    ecodes.KEY_LEFTCTRL: ecodes.KEY_LEFTCTRL,
    ecodes.KEY_LEFTSHIFT: ecodes.KEY_LEFTSHIFT,
    ecodes.KEY_LEFTALT: ecodes.KEY_LEFTALT,
    ecodes.KEY_LEFTMETA: ecodes.KEY_LEFTMETA,

    ecodes.KEY_RIGHTCTRL: ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_RIGHTSHIFT: ecodes.KEY_RIGHTSHIFT,
    ecodes.KEY_RIGHTALT: ecodes.KEY_RIGHTALT,
    ecodes.KEY_RIGHTMETA: ecodes.KEY_RIGHTMETA,

    ecodes.KEY_I: ecodes.KEY_UP,
    ecodes.KEY_J: ecodes.KEY_LEFT,
    ecodes.KEY_K: ecodes.KEY_DOWN,
    ecodes.KEY_L: ecodes.KEY_RIGHT,

    ecodes.KEY_H: ecodes.KEY_BACKSPACE,
    ecodes.KEY_N: ecodes.KEY_ENTER,
    ecodes.KEY_M: ecodes.KEY_DELETE,

    ecodes.KEY_U: ecodes.KEY_HOME,
    ecodes.KEY_O: ecodes.KEY_END,
    ecodes.KEY_APOSTROPHE: ecodes.KEY_PAGEUP,
    ecodes.KEY_SLASH: ecodes.KEY_PAGEDOWN,

    ecodes.KEY_1: ecodes.KEY_F1,
    ecodes.KEY_2: ecodes.KEY_F2,
    ecodes.KEY_3: ecodes.KEY_F3,
    ecodes.KEY_4: ecodes.KEY_F4,
    ecodes.KEY_5: ecodes.KEY_F5,
    ecodes.KEY_6: ecodes.KEY_F6,
    ecodes.KEY_7: ecodes.KEY_F7,
    ecodes.KEY_8: ecodes.KEY_F8,
    ecodes.KEY_9: ecodes.KEY_F9,
    ecodes.KEY_0: ecodes.KEY_F10,
    ecodes.KEY_MINUS: ecodes.KEY_F11,
    ecodes.KEY_EQUAL: ecodes.KEY_F12,
}


def _write_event(ui: UInput, event: InputEvent):
    if event.type == ecodes.EV_KEY:
        state.update_pressed_keys(event)

        key_state = ('up', 'down', 'hold')[event.value]
        key = ecodes.keys.get(event.code)
        _logger.debug('write event:\t%s\t%s', key, key_state)

    ui.write_event(event)


async def _first_fn_key_press(ui: UInput):
    await asyncio.sleep(FIRST_KEY_DELAY)

    _logger.debug('CALLBACK')
    if not state.is_fn_active:
        return

    if not state.first_fn_event_passed:
        state.first_fn_event_passed = True
        _handle_fn_event(ui, state.first_fn_event)


def _handle_fn_event(ui: UInput, event: InputEvent):
    if event.type == ecodes.EV_KEY:
        key_code = event.code

        if key_code == ecodes.KEY_SPACE:
            return

        # pass the event unmodified if the key was pressed before FN layer activated
        if key_code not in state.pressed_keys:
            if not state.first_fn_event:
                state.first_fn_event = event
                asyncio.create_task(_first_fn_key_press(ui))
                return

            if not state.first_fn_event_passed:
                state.first_fn_event_passed = True
                _handle_fn_event(ui, state.first_fn_event)

            if key_code not in _keycodes:
                return

            event.code = _keycodes[key_code]

            if event.value == KeyEvent.key_down:
                state.release_key_codes[key_code] = event.code
                state.is_fn_used = True
            elif event.value == KeyEvent.key_up:
                state.release_key_codes.pop(key_code, None)

    _write_event(ui, event)


def _write_space(ui: UInput, key_down_event: InputEvent):
    _write_event(ui, InputEvent(
        key_down_event.sec,
        key_down_event.usec,
        ecodes.EV_KEY,
        ecodes.KEY_SPACE,
        KeyEvent.key_down
    ))
    _write_event(ui, key_down_event)


def _handle_events(ui: UInput, events: Generator[InputEvent, None, None]):
    for event in events:
        if event.type == ecodes.EV_KEY and event.code == ecodes.KEY_SPACE:
            if event.value == KeyEvent.key_down and not state.is_fn_active:
                state.activate_fn_layer(event)

            elif event.value == KeyEvent.key_up:
                state.deactivate_fn_layer()
                if not state.is_fn_used and event.timestamp() - state.fn_activate_time < MOD_THRESHOLD:
                    _write_space(ui, event)

                    if state.first_fn_event and not state.first_fn_event_passed:
                        if (event.timestamp() - state.first_fn_event.timestamp()) < FIRST_KEY_DELAY:
                            _write_event(ui, state.first_fn_event)

        elif event.type == ecodes.EV_KEY and state.is_fn_active:
            _handle_fn_event(ui, event)
        elif event.type == ecodes.EV_KEY and event.value in (KeyEvent.key_up, KeyEvent.key_hold):
            # modify `event.code` if fn-layer key was released after FN layer deactivated
            event.code = state.release_key_codes.pop(event.code, event.code)

            if event.code not in state.pressed_keys:
                continue

            _write_event(ui, event)
        else:
            _write_event(ui, event)

    _logger.debug(state.pressed_keys)
    ui.syn()


async def main():
    dev = InputDevice('/dev/input/by-id/usb-SEM_USB_Keyboard-event-kbd')

    with UInput() as ui:
        with dev.grab_context():
            while True:
                try:
                    state.dev_read_future = dev.async_read()
                    _handle_events(ui, await state.dev_read_future)
                except Shutdown:
                    _logger.info('Shutting down')
                    loop.remove_reader(dev.fileno())
                    break


def _raise_shutdown():
    if state.dev_read_future:
        state.dev_read_future.set_exception(Shutdown())


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s %(asctime)s %(name)s %(message)s')

    _logger.info('Starting')

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, _raise_shutdown)
    loop.add_signal_handler(signal.SIGTERM, _raise_shutdown)

    asyncio.get_event_loop().run_until_complete(main())
