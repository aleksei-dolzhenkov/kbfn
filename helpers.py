from __future__ import annotations

from typing import Dict

from evdev.ecodes import ecodes


def convert_keycode_map(codes: Dict[int | str, int | str]):
    res = {}

    for k, v in codes.items():
        k = ecodes[k] if isinstance(k, str) else k
        v = ecodes[v] if isinstance(v, str) else v
        res[k] = v

    return res
