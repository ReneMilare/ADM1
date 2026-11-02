from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from simulator.mcp_server import _ConvertASM1Params, convert_asm1_to_adm1_influent, list_extensions


EXPECTED_TOOLS = {
    "simulate_reactor",
    "simulate_codigestion",
    "simulate_two_phase",
    "simulate_tpad",
    "simulate_batch",
    "get_biogas_production",
    "get_vfa_profile",
    "get_ph_profile",
    "compare_backends",
    "compare_scenarios",
    "optimize_parameter",
    "calibrate_model",
    "run_phase3_validation",
    "design_reactor",
    "list_extensions",
    "convert_asm1_to_adm1_influent",
    "run_digital_twin_scenario",
}


def test_stdio_tool_registration_and_json_calls() -> None:
    async def check() -> None:
        params = StdioServerParameters(command=sys.executable, args=["-m", "simulator.mcp_server"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                tools = {tool.name: tool for tool in listing.tools}
                assert set(tools) == EXPECTED_TOOLS
                assert tools["list_extensions"].input_schema["properties"] == {}
                conversion_schema = tools["convert_asm1_to_adm1_influent"].input_schema
                assert conversion_schema["required"] == ["params"]
                assert conversion_schema["$defs"]["_ConvertASM1Params"]["additionalProperties"] is False

                for name, arguments, expected in (
                    ("list_extensions", {}, await list_extensions()),
                    (
                        "convert_asm1_to_adm1_influent",
                        {"params": {}},
                        await convert_asm1_to_adm1_influent(_ConvertASM1Params()),
                    ),
                ):
                    result = await session.call_tool(name, arguments)
                    assert not result.is_error
                    assert len(result.content) == 1
                    assert result.content[0].type == "text"
                    assert json.loads(result.content[0].text) == json.loads(expected)

    asyncio.run(check())
