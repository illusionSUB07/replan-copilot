"""python -m thread [scenario ...]: impact of product changes across configs, mix, slots and sequence."""
import json
import sys

from .impact import analyse
from .product import SCENARIOS

for name in sys.argv[1:] or SCENARIOS:
    print(json.dumps(analyse(name)[0], indent=2))
