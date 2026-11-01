from mcp.server import MCPServer
from mcp.types import ToolAnnotations

app = MCPServer('codex-ops-probe')


@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def fixture() -> dict:
    """Return a deterministic fixture with nested values and a large body."""
    return {'marker': 'RAW_VALUE_SENTINEL', 'records': [{'id': n, 'text': 'x' * 100} for n in range(400)],
            'nested': {'null': None, 'bool': False, 'unicode': '完整值'}, 'last': 399}


app.run()
