import asyncio

from evdev import InputDevice, InputEvent, UInput


class InputDeviceReader:
    _fut: asyncio.Future = None
    _closed: bool = False

    def __init__(self, dev: InputDevice):
        self._dev = dev

    def __aiter__(self):
        return self.reader()

    def close(self):
        self._closed = True
        if self._fut and not self._fut.done():
            self._fut.set_exception(StopAsyncIteration)

    async def reader(self):
        with self._dev.grab_context():
            while True:
                if self._closed:
                    break

                self._fut = self._dev.async_read()

                try:
                    for event in await self._fut:
                        yield event
                except StopAsyncIteration:
                    asyncio.get_event_loop().remove_reader(self._dev.fileno())
                    break


class AbstractLayer:

    def send(self, event: InputEvent):
        raise NotImplemented


class ModLayer(AbstractLayer):

    def configure(self, **kwargs):
        ...

    def __init__(self, out: AbstractLayer, **kwargs):
        self.out = out
        self.configure(**kwargs)


class EventWriter(AbstractLayer):

    def __init__(self, ui: UInput):
        self.ui = ui

    def send(self, event: InputEvent):
        self.ui.write_event(event)
        self.ui.syn()
