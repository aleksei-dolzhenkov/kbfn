import json
import sys
import asyncio
import logging
import signal
import time
from typing import Dict, Optional

import evdev
from evdev import InputDevice, UInput

from base import AbstractLayer, EventWriter, InputDeviceReader
from dual_role_layer import DualRoleSwitchLayer
from remap_layer import RemapLayer


TLayers = Dict[int, AbstractLayer]
logger = logging.getLogger('kbfn')


def _get_device_by_name(name: str) -> Optional[InputDevice]:
    for x in evdev.list_devices():
        dev = InputDevice(x)
        logger.debug('%s -> %s', dev.name, x)
        if dev.name == name:
            return dev


_LAYERS = {
    "Remap": RemapLayer,
    "DualRole": DualRoleSwitchLayer,
}


class KBFN:

    def __init__(self, dev: InputDevice, config: dict):
        self.input_reader = InputDeviceReader(dev)
        self.config = config  # fixme: validate settings

    async def run(self):
        with UInput() as ui:
            writer = EventWriter(ui)

            for _layer in reversed(self.config['layers']):
                _layer = _layer.copy()
                cls = _LAYERS[_layer.pop('type')]
                writer = cls(writer, **_layer)

            # mod_layer = DualRoleSwitchLayer(out=writer)
            # remap_layer = RemapLayer(out=mod_layer)

            async for event in self.input_reader:
                writer.send(event)

    def close(self):
        self.input_reader.close()


class NoDeviceFound(Exception):
    pass


def watcher(config):
    _finished = False

    while not _finished:
        print('111')
        try:
            runner(config)
            _finished = True
        except (NoDeviceFound, OSError):
            pass


class Watcher:
    _finished = False

    def __init__(self, config):
        self.config = config

    def stop(self):
        print('bye')
        self._finished = True

    def run(self):
        def _asd(_signal, _frame):
            print('asd')
            self.stop()

        signal.signal(signal.SIGINT, _asd)
        signal.signal(signal.SIGTERM, _asd)

        while not self._finished:
            try:
                runner(self.config)
                self.stop()
            except (NoDeviceFound, OSError) as e:
                logger.debug(e)
                time.sleep(3)


def runner(config):
    dev_name = config['device']
    dev = _get_device_by_name(dev_name)
    if not dev:
        raise NoDeviceFound('No device found %s' % dev_name)

    kbfn = KBFN(dev, config)
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, kbfn.close)
    loop.add_signal_handler(signal.SIGTERM, kbfn.close)
    loop.run_until_complete(kbfn.run())


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(levelname)s %(asctime)s %(name)s %(message)s'
    )

    args = sys.argv[1:]

    if not args:
        print('usage kbfn <config.json>')
        exit(1)

    with open(args[0]) as f:
        _config = json.load(f)

    Watcher(_config).run()
