"""Internal Worker module entry point."""
from pathlib import Path
import sys
from actio.adapters.runtime.host import main
if __name__ == '__main__':
    main(Path(sys.argv[1]))
