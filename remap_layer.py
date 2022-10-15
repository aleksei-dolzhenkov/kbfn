import logging

from typing import Dict, Union
from evdev import InputEvent, ecodes

from base import ModLayer
from helpers import convert_keycode_map


logger = logging.getLogger(__name__)


class RemapLayer(ModLayer):
    _codes: Dict = None

    def configure(self, codes: Dict[Union[int, str], Union[int, str]] = None):
        self._codes = convert_keycode_map(codes or {})

    def send(self, event: InputEvent):
        if event.type == ecodes.EV_KEY:
            if event.code in self._codes:
                event.code = self._codes[event.code]
                logger.debug('remap %s', event.code)

        self.out.send(event)
