"""Internal MCP child module entry point."""
import asyncio
from pathlib import Path
import sys
from actio.adapters.runtime.mcp_server import main
if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1])))
