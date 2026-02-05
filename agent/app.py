import asyncio
import json
import os

from mcp import Resource
from mcp.types import Prompt

from agent.mcp_client import MCPClient
from agent.dial_client import DialClient
from agent.models.message import Message, Role
from agent.prompts import SYSTEM_PROMPT


# https://remote.mcpservers.org/fetch/mcp
# Pay attention that `fetch` doesn't have resources and prompts
DIAL_ENDPOINT = "https://ai-proxy.lab.epam.com"
API_KEY = os.getenv('DIAL_API_KEY')

async def main():
    api_key = API_KEY
    endpoint = DIAL_ENDPOINT
    if not api_key or not endpoint:
        raise RuntimeError("AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set")

    async with MCPClient("http://localhost:8005/mcp") as mcp_client:
        resources: list[Resource] = await mcp_client.get_resources()
        if resources:
            print("🔗 MCP Resources:")
            for resource in resources:
                print(f"  - {resource.uri} ({resource.mimeType})")
        else:
            print("🔗 MCP Resources: none")

        tools = await mcp_client.get_tools()
        if tools:
            print("🛠️ MCP Tools:")
            for tool in tools:
                print(f"  - {tool['function']['name']}: {tool['function']['description']}")
        else:
            print("🛠️ MCP Tools: none")

        prompts: list[Prompt] = await mcp_client.get_prompts()
        if prompts:
            print("📝 MCP Prompts:")
            for prompt in prompts:
                print(f"  - {prompt.name}: {prompt.description}")
        else:
            print("📝 MCP Prompts: none")

        dial_client = DialClient(api_key=api_key, endpoint=endpoint, tools=tools, mcp_client=mcp_client)

        messages: list[Message] = [Message(role=Role.SYSTEM, content=SYSTEM_PROMPT)]
        for prompt in prompts:
            try:
                prompt_content = await mcp_client.get_prompt(prompt.name)
            except Exception as exc:
                print(f"⚠️ Failed to load prompt '{prompt.name}': {exc}")
                continue
            messages.append(Message(role=Role.USER, name=prompt.name, content=prompt_content))

        print("\nType 'exit', 'quit', or 'q' to leave the chat.\n")
        while True:
            try:
                user_input = (await asyncio.to_thread(input, "👤 > ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Ending chat.")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                print("👋 Ending chat.")
                break

            messages.append(Message(role=Role.USER, content=user_input))

            try:
                ai_message = await dial_client.get_completion(messages)
            except Exception as exc:
                print(f"❌ Assistant error: {exc}")
                continue

            messages.append(ai_message)
            if ai_message.content:
                print(f"🤖: {ai_message.content}\n")


if __name__ == "__main__":
    asyncio.run(main())
