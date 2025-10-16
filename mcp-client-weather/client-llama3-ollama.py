import asyncio
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ollama import AsyncClient
import re, json

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.client = AsyncClient()
        print("🦙 Ollama Llama3 Ready!")

    async def connect_to_server(self, server_script_path: str):
        """Connect to MCP (weather) server via stdio"""
        if not (server_script_path.endswith(".py") or server_script_path.endswith(".js")):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if server_script_path.endswith(".py") else "node"
        server_params = StdioServerParameters(command=command, args=[server_script_path])

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()
        response = await self.session.list_tools()
        print("\n🔌 Connected to MCP server with tools:", [t.name for t in response.tools])

    async def _call_llama(self, messages):
        """Call local Llama3 (Ollama)"""
        response = await self.client.chat(model="llama3.2:1b", messages=messages)
        message = response["message"]
        return message["content"]

    async def _detect_weather_tool_call(self, text: str):
        """
        Detect tool call for weather tasks (get_alerts or get_forecast)
        Expected JSON example:
        {"name": "get_forecast", "arguments": {"latitude": 37.77, "longitude": -122.42}}
        """
        text = text.strip()

        # 1️⃣ Try to extract JSON first
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if not match:
            match = re.search(r'(\{.*"name".*\})', text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(1))
                if "name" in obj:
                    return obj
            except json.JSONDecodeError:
                pass

        # 2️⃣ Fallback heuristic for plain text
        lowered = text.lower()

        # → detect get_forecast
        if "forecast" in lowered or "temperature" in lowered or "weather" in lowered:
            latlon = re.findall(r'(-?\d{1,2}\.\d+)[,\s]+(-?\d{1,3}\.\d+)', text)
            if latlon:
                lat, lon = map(float, latlon[0])
                return {"name": "get_forecast", "arguments": {"latitude": lat, "longitude": lon}}
            # fallback: prompt model to clarify later
            return {"name": "get_forecast", "arguments": {}}

        # → detect get_alerts
        state_match = re.search(r'\b(?:in|for|state)\s+([A-Za-z]{2})\b', text)
        if "alert" in lowered or "warning" in lowered or "storm" in lowered:
            if state_match:
                state = state_match.group(1).upper()
                return {"name": "get_alerts", "arguments": {"state": state}}
            return {"name": "get_alerts", "arguments": {}}

        return None

    async def process_query(self, query: str) -> str:
        """
        Main pipeline for the weather MCP server:
        - Ask Llama3
        - Detect weather tool (get_forecast/get_alerts)
        - Execute tool via MCP
        - Feed result back to model for final summary
        """
        system_msg = (
            "You are a helpful weather assistant. "
            "You have access to these tools:\n"
            "1️⃣ get_alerts(state: str) — get weather alerts for a U.S. state (e.g., CA, NY)\n"
            "2️⃣ get_forecast(latitude: float, longitude: float) — get a 5-period forecast for given coordinates.\n\n"
            "When you want to use a tool, output ONLY a JSON object like this:\n"
            '{"name": "get_forecast", "arguments": {"latitude": 37.77, "longitude": -122.42}}'
        )

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": query}
        ]

        # Step 1: Ask model
        response_text = await self._call_llama(messages)
        print(f"🧠 Model raw output:\n{response_text}\n")
        final_output = [response_text]

        # Step 2: Detect weather tool
        tool_call = await self._detect_weather_tool_call(response_text)
        print(f"🔎 Detected tool call: {tool_call}")

        if tool_call:
            tool_name = tool_call["name"]
            args = tool_call.get("arguments", {})

            # Coerce args to dict
            if isinstance(args, list) and args:
                args = args[0] if isinstance(args[0], dict) else {}
            elif not isinstance(args, dict):
                args = {}

            print(f"⚙️ Calling {tool_name} with args: {args}")

            try:
                tool_result = await self.session.call_tool(tool_name, args)

                # Extract readable text
                if getattr(tool_result, "content", None):
                    tool_output = ""
                    for item in tool_result.content:
                        if hasattr(item, "text"):
                            tool_output += item.text
                        elif isinstance(item, dict) and "text" in item:
                            tool_output += item["text"]
                        else:
                            tool_output += str(item)
                else:
                    tool_output = str(tool_result)

                print(f"📦 Tool Output (truncated):\n{tool_output[:400]}\n")

                # Step 3: Ask model to summarize result
                messages.extend([
                    {"role": "assistant", "content": response_text},
                    {"role": "tool", "content": f"Tool {tool_name} result:\n{tool_output}"}
                ])
                followup_text = await self._call_llama(messages)
                final_output.append(followup_text)

            except Exception as e:
                print(f"❌ Tool call failed: {e}")
                final_output.append(f"[Tool call error: {e}]")

        else:
            print("⚠️ No tool detected — returning model output as-is.")

        return "\n".join(final_output)

    async def chat_loop(self):
        print("\n🦙 LOCAL Llama3 + MCP Client Started!")
        print("Type a query like:")
        print("→ 'What’s the weather forecast for latitude 37.77 and longitude -122.42?'")
        print("→ 'Are there any weather alerts in CA?'")
        print("Type 'quit' to exit.\n")

        while True:
            try:
                query = input("Query: ").strip()
                if query.lower() == "quit":
                    break
                result = await self.process_query(query)
                print("\n🗨️ " + result + "\n")
            except Exception as e:
                print(f"❌ Error: {e}")

    async def cleanup(self):
        await self.exit_stack.aclose()


async def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python local_llama_client.py <server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
