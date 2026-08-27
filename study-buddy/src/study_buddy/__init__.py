import sys
from pathlib import Path

# Add parent directory to path to import main.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from main import main as _main

def main() -> None:
    import asyncio
    asyncio.run(_main())
