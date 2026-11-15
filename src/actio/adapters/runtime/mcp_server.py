"""Official MCP server with a single fixed synthetic read-only dataset."""
import asyncio
import json
import os
from pathlib import Path
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

SCHEMA = {'type':'object','properties':{'key':{'type':'string'},'op':{'type':'string'}},
          'required':['key','op'],'additionalProperties':False}
DESCRIPTION = 'Read one synthetic fixture key.'
DATA = {'ok': 'SYNTHETIC_SHARED_REFERENCE_17'}


async def main(root):
    server = Server('actio-synthetic',version='1')
    def record(row):
        with (root/'mcp.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
    @server.list_tools()
    async def tools():
        record({'kind':'discovery','protocol':server.request_context.session.client_params.protocolVersion})
        return [types.Tool(name='read_fixture',description=DESCRIPTION,inputSchema=SCHEMA,
            annotations=types.ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False))]
    @server.call_tool()
    async def call(name, arguments):
        if name != 'read_fixture' or set(arguments) != {'key','op'} or arguments['key'] not in DATA or not isinstance(arguments['op'],str):
            raise ValueError('outside synthetic scope')
        record({'kind':'received','name':name,'arguments':arguments,'pid':os.getpid()})
        return [types.TextContent(type='text',text=DATA[arguments['key']])]
    async with stdio_server() as (rx,tx):
        await server.run(rx,tx,server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1])))
