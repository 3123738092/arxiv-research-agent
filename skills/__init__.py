import sys
from pathlib import Path

# 把 ~/.workbuddy/ 加入 sys.path，使 skills 能作为顶层包被 import
_parent = str(Path(__file__).resolve().parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# skills package
