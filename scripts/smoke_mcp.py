from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    env = dict(os.environ)
    env.update(
        {
            "ABSTRATOR_LLM_PROVIDER": "fake",
            "ABSTRATOR_DATA_DIR": str(ROOT / "data"),
            "ABSTRATOR_RUNS_DIR": str(ROOT / "runs"),
        }
    )
    params = StdioServerParameters(
        command=str(ROOT / ".venv" / "Scripts" / "abstrator.exe"),
        args=["mcp"],
        env=env,
    )

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        print("servidor:", init.server_info.name, init.server_info.version)

        tools = await session.list_tools()
        print("ferramentas:", ", ".join(sorted(t.name for t in tools.tools)))

        resources = await session.list_resources()
        print("resources:", ", ".join(str(r.uri) for r in resources.resources))

        result = await session.call_tool(
            "assess_complexity", {"concept": "arquitetura de agentes", "goal": "planejar"}
        )
        payload = json.loads(result.content[0].text)
        print("assess_complexity ->", payload["complexity"]["verdict"], "|", payload["hint"])
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
