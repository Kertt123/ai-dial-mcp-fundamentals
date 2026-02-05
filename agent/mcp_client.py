from typing import Optional, Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.types import (
    CallToolResult,
    TextContent,
    GetPromptResult,
    ReadResourceResult,
    Resource,
    TextResourceContents,
    BlobResourceContents,
    Prompt,
)
from pydantic import AnyUrl


class MCPClient:
    """Handles MCP server connection and tool execution"""

    def __init__(self, server_parameters: StdioServerParameters) -> None:
        self.server_parameters = server_parameters
        self.session: Optional[ClientSession] = None
        self._stdio_context = None
        self._session_context = None

    async def __aenter__(self):
        self._stdio_context = stdio_client(self.server_parameters)
        streams = await self._stdio_context.__aenter__()
        if isinstance(streams, tuple):
            if len(streams) == 3:
                read_stream, write_stream, _ = streams
            elif len(streams) == 2:
                read_stream, write_stream = streams
            else:
                raise RuntimeError("Unexpected stdio_client return value")
        else:
            read_stream, write_stream = streams
        self._session_context = ClientSession(read_stream, write_stream)
        self.session = await self._session_context.__aenter__()
        capabilities = await self.session.initialize()
        print(f"[MCP] Session initialized: {capabilities}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._session_context is not None:
                await self._session_context.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self.session = None
            self._session_context = None

        if self._stdio_context is not None:
            await self._stdio_context.__aexit__(exc_type, exc_val, exc_tb)
            self._stdio_context = None

    async def get_tools(self) -> list[dict[str, Any]]:
        """Get available tools from MCP server"""
        if not self.session:
            raise RuntimeError("MCP client not connected. Call connect() first.")
        tools_result = await self.session.list_tools()
        tool_items = getattr(tools_result, "tools", tools_result) or []
        dial_tools: list[dict[str, Any]] = []
        for tool in tool_items:
            schema = self._schema_to_dict(getattr(tool, "input_schema", None))
            dial_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": getattr(tool, "name", ""),
                        "description": getattr(tool, "description", ""),
                        "parameters": schema,
                    },
                }
            )
        return dial_tools

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        """Call a specific tool on the MCP server"""
        if not self.session:
            raise RuntimeError("MCP client not connected. Call connect() first.")

        tool_result: CallToolResult = await self.session.call_tool(tool_name, tool_args)
        contents = getattr(tool_result, "content", []) or []
        if not contents:
            print("    ⚙️: <empty>\n")
            return None

        content = contents[0]
        print(f"    ⚙️: {content}\n")
        if isinstance(content, TextContent):
            return content.text
        return content

    async def get_resources(self) -> list[Resource]:
        """Get available resources from MCP server"""
        if not self.session:
            raise RuntimeError("MCP client not connected.")
        try:
            resource_result = await self.session.list_resources()
            return getattr(resource_result, "resources", resource_result) or []
        except Exception as exc:
            print(f"[MCP] list_resources failed: {exc}")
            return []

    async def get_resource(self, uri: AnyUrl) -> str | bytes:
        """Get specific resource content"""
        if not self.session:
            raise RuntimeError("MCP client not connected.")

        resource_result: ReadResourceResult = await self.session.read_resource({"uri": str(uri)})
        contents = getattr(resource_result, "contents", []) or []
        if not contents:
            raise ValueError(f"Resource {uri} returned no contents")

        content = contents[0]
        if isinstance(content, TextResourceContents):
            return content.text
        if isinstance(content, BlobResourceContents):
            return content.blob
        return content

    async def get_prompts(self) -> list[Prompt]:
        """Get available prompts from MCP server"""
        if not self.session:
            raise RuntimeError("MCP client not connected.")
        try:
            prompt_result = await self.session.list_prompts()
            return getattr(prompt_result, "prompts", prompt_result) or []
        except Exception as exc:
            print(f"[MCP] list_prompts failed: {exc}")
            return []

    async def get_prompt(self, name: str) -> str:
        """Get specific prompt content"""
        if not self.session:
            raise RuntimeError("MCP client not connected.")
        prompt_result: GetPromptResult = await self.session.get_prompt(name)
        combined_content = ""
        for message in getattr(prompt_result, "messages", []) or []:
            combined_content += self._message_content_to_text(getattr(message, "content", message))
        return combined_content.strip()

    @staticmethod
    def _schema_to_dict(schema: Any) -> dict[str, Any]:
        if schema is None:
            return {"type": "object", "properties": {}}
        if isinstance(schema, dict):
            return schema
        if hasattr(schema, "model_dump"):
            return schema.model_dump()
        if hasattr(schema, "dict"):
            return schema.dict()
        if hasattr(schema, "to_dict"):
            return schema.to_dict()
        return {"type": "object"}

    def _message_content_to_text(self, content: Any) -> str:
        if isinstance(content, list):
            return "".join(self._message_content_to_text(item) for item in content)
        if isinstance(content, TextContent):
            return content.text + "\n"
        if isinstance(content, str):
            return content + "\n"
        if hasattr(content, "text"):
            return f"{content.text}\n"
        return f"{content}\n"
