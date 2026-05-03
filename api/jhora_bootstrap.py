"""One-time Swiss Ephemeris + PyJHora defaults for server processes."""
import os
import threading

import swisseph as swe

from jhora import const

_lock = threading.Lock()
_initialized = False


def init_jhora() -> None:
    global _initialized
    with _lock:
        if _initialized:
            return
        ephe = os.path.join(os.path.dirname(const.__file__), "data", "ephe")
        swe.set_ephe_path(ephe)
        # Mean nodes work with the minimal ephe shipped on PyPI; true node needs full JPL files.
        const.set_node_mode(False)
        _initialized = True
