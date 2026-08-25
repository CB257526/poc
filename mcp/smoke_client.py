"""对正在运行的远端 MCP 服务打一遍 tools / resources / prompts。"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import Client

URL = os.getenv("WORKFLOW_MCP_URL", "http://127.0.0.1:8100/mcp")


def _payload(result) -> object:
    if getattr(result, "structured_content", None):
        raw = result.structured_content.get("result", result.structured_content)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        return raw
    texts = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    return texts


def show(title: str, data, limit: int = 1600) -> None:
    print(f"\n===== {title} =====")
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = str(data)
    print(text[:limit])
    if len(text) > limit:
        print(f"... ({len(text)} chars)")


async def main() -> int:
    async with Client(URL) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
        show("tools", [t.name for t in tools.tools])
        show("resources", [str(r.uri) for r in resources.resources])
        show("templates", [t.uri_template for t in templates.resource_templates])
        show("prompts", [p.name for p in prompts.prompts])

        missing_file = _payload(await client.call_tool("start_run", {
            "input_file": "./table/does-not-exist.xlsx",
        }))
        show("tool start_run missing file", missing_file)

        schema = _payload(await client.call_tool("get_workflow_schema", {}))
        show("tool get_workflow_schema", schema, 800)

        listed = _payload(await client.call_tool("list_runs", {"limit": 5}))
        show("tool list_runs", listed)
        runs = listed.get("runs") if isinstance(listed, dict) else []
        if not runs:
            print("\n没有运行记录。先执行: uv run workflow run --input ./table/1-链接.xlsx")
            return 1
        run_id = runs[0]["run_id"]
        print(f"\n使用 run_id = {run_id}")

        overview = _payload(await client.call_tool("get_run", {"run_id": run_id}))
        show("tool get_run", overview)

        node_ids = [item["node_id"] for item in overview.get("nodes") or []] or ["node_00"]
        first_node = node_ids[0]
        node_view = _payload(await client.call_tool("get_node", {
            "run_id": run_id,
            "node_id": first_node,
            "sample_size": 3,
        }))
        show(f"tool get_node {first_node}", node_view)

        issues = _payload(await client.call_tool("list_issues", {"run_id": run_id}))
        show("tool list_issues", issues)

        summarized = _payload(await client.call_tool("summarize_issues", {"run_id": run_id}))
        show("tool summarize_issues", summarized)

        records = _payload(await client.call_tool("list_records", {
            "run_id": run_id,
            "limit": 5,
        }))
        show("tool list_records", records)

        funnel = _payload(await client.call_tool("get_funnel", {"run_id": run_id}))
        show("tool get_funnel", funnel)

        waited = _payload(await client.call_tool("wait_run", {
            "run_id": run_id,
            "timeout_seconds": 1,
            "interval_seconds": 0.5,
        }))
        show("tool wait_run", waited)

        sample = ((node_view.get("output_summary") or {}).get("sample") or [{}])[0]
        record_id = sample.get("id") or "rec_0001"
        record = _payload(await client.call_tool("get_record", {
            "run_id": run_id,
            "record_id": record_id,
        }))
        show(f"tool get_record {record_id}", record)

        artifacts = _payload(await client.call_tool("list_artifacts", {"run_id": run_id}))
        show("tool list_artifacts", artifacts)
        keys = [item["key"] for item in artifacts.get("artifacts") or []]
        if keys:
            described = _payload(await client.call_tool("describe_artifact", {
                "run_id": run_id,
                "file_key": keys[0],
            }))
            show(f"tool describe_artifact {keys[0]}", described)

        missing = _payload(await client.call_tool("get_run", {"run_id": "does_not_exist"}))
        show("tool get_run missing", missing)

        schema_res = await client.read_resource("workflow://schema")
        show("resource workflow://schema", schema_res.contents[0].text[:500] if schema_res.contents else schema_res)
        runs_res = await client.read_resource("workflow://runs")
        show("resource workflow://runs", runs_res.contents[0].text[:500] if runs_res.contents else runs_res)
        run_res = await client.read_resource(f"workflow://runs/{run_id}")
        show(f"resource workflow://runs/{run_id}", run_res.contents[0].text[:500] if run_res.contents else run_res)
        node_res = await client.read_resource(f"workflow://runs/{run_id}/nodes/{first_node}")
        show(
            f"resource workflow://runs/{run_id}/nodes/{first_node}",
            node_res.contents[0].text[:500] if node_res.contents else node_res,
        )
        issues_res = await client.read_resource(f"workflow://runs/{run_id}/issues")
        show(
            f"resource workflow://runs/{run_id}/issues",
            issues_res.contents[0].text[:500] if issues_res.contents else issues_res,
        )

        for name, args in [
            ("run_workflow", {"input_file": "./table/1-链接.xlsx"}),
            ("inspect_run", {"run_id": run_id}),
            ("inspect_node", {"run_id": run_id, "node_id": first_node}),
            ("explain_record", {"run_id": run_id, "record_id": record_id}),
        ]:
            prompt = await client.get_prompt(name, args)
            text = prompt.messages[0].content.text if prompt.messages else str(prompt)
            show(f"prompt {name}", text)

    print("\n全部工具 / 资源 / 提示词请求完成")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
