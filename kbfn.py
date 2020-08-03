import asyncio
import logging
import signal

from evdev import InputDevice, UInput

from base import EventWriter, InputDeviceReader
from dual_role import DualRoleFn


class KBFN:

    def __init__(self, dev: InputDevice):
        self.input_reader = InputDeviceReader(dev)

    async def run(self):
        with UInput() as ui:
            writer = EventWriter(ui)
            mod_layer = DualRoleFn(out=writer)
            async for event in self.input_reader:
                mod_layer.send(event)

    def close(self):
        self.input_reader.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s %(asctime)s %(name)s %(message)s'
    )

    kbfn = KBFN(InputDevice('/dev/input/by-id/usb-SEM_USB_Keyboard-event-kbd'))

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, kbfn.close)
    loop.add_signal_handler(signal.SIGTERM, kbfn.close)
    loop.run_until_complete(kbfn.run())
