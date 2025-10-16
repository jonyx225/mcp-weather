import asyncio
import json
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch

load_dotenv()

class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # ← LOCAL LLAMA3 (NO API KEY!)
        print("🦙 Loading Llama3 locally...")
        model_id = "meta-llama/Llama-3.1-8B-Instruct"  # 8B = fast on most machines
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float16,  # Faster, less memory
            device_map="auto",          # GPU if available
        )
        self.pipe = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            device_map="auto"
        )
        print("✅ Llama3 loaded locally!")

    async def connect_to_server(self, server_script_path: str):
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
            
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(command=command, args=[server_script_path], env=None)
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        response = await self.session.list_tools()
        print("\nConnected to server with tools:", [tool.name for tool in response.tools])

    def _format_tools_openai(self, mcp_tools):
        """Convert MCP tools to OpenAI format"""
        return [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in mcp_tools]

    def _call_llama3(self, messages, tools=None):
        """Call local Llama3 with tool support"""
        # Convert messages to prompt
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"<|start_header_id|>system<|end_header_id|>\n{msg['content']}<|eot_id|>\n"
            elif msg["role"] == "user":
                prompt += f"<|start_header_id|>user<|end_header_id|>\n{msg['content']}<|eot_id|>\n"
            elif msg["role"] == "assistant":
                prompt += f"<|start_header_id|>assistant<|end_header_id|>\n{msg['content']}<|eot_id|>\n"
        
        # Add tools to prompt if present
        if tools:
            tools_str = json.dumps(tools, indent=2)
            prompt += f"<|start_header_id|>user<|end_header_id|>\nYou have these tools: {tools_str}. Use them when needed.<|eot_id|>\n<|start_header_id|>assistant<|end_header_id|>\n"
        
        prompt += "<|start_header_id|>assistant<|end_header_id|>\n"

        # Generate
        outputs = self.pipe(
            prompt,
            max_new_tokens=500,
            temperature=0.1,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        response = outputs[0]["generated_text"]
        # Extract assistant response
        assistant_response = response.split("<|start_header_id|>assistant<|end_header_id|>\n")[-1]
        assistant_response = assistant_response.split("<|eot_id|>")[0].strip()
        
        # Simple tool detection (Llama3 will output JSON)
        if "```json" in assistant_response or "{" in assistant_response:
            try:
                # Extract JSON tool call
                start = assistant_response.find("{")
                end = assistant_response.rfind("}") + 1
                tool_json = json.loads(assistant_response[start:end])
                return {
                    "content": assistant_response.replace(str(tool_json), "").strip(),
                    "tool_calls": [{"function": {"name": tool_json.get("name"), "arguments": json.dumps(tool_json.get("arguments", {}))}}
                ] if "name" in tool_json else None
                }
            except:
                pass
        
        return {"content": assistant_response, "tool_calls": None}

    async def process_query(self, query: str) -> str:
        messages = [{"role": "user", "content": query}]
        
        mcp_response = await self.session.list_tools()
        tools = self._format_tools_openai(mcp_response.tools)
        
        # First Llama3 call
        llama_response = self._call_llama3(messages, tools)
        final_text = [llama_response["content"]]
        
        # Handle tool calls
        if llama_response["tool_calls"]:
            for tool_call in llama_response["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"\n[Called {tool_name}: {tool_args} → {result.content}]")
                
                # Continue conversation
                messages.append({"role": "assistant", "content": llama_response["content"]})
                messages.append({"role": "user", "content": f"Tool result: {result.content}"})
                
                # Second Llama3 call
                llama_response = self._call_llama3(messages)
                final_text.append(llama_response["content"])
        
        return "\n".join(final_text)

    async def chat_loop(self):
        print("\n🦙 LOCAL Llama3 MCP Client Started! (No API needed)")
        print("Type queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() == 'quit':
                    break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        await self.exit_stack.aclose()

# ← SAME MAIN FUNCTION
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