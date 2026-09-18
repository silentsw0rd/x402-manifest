import os
from langchain_ollama import ChatOllama
from x402_tool import x402_paid_web_extractor

os.environ["CLIENT_PRIVATE_KEY"] = "0x<YOUR_CLIENT_PRIVATE_KEY>"
os.environ["GATEWAY_URL"] = "https://your-ngrok-domain.ngrok-free.app/api/v1/extract"

# Bind tool to local Ollama model
llm = ChatOllama(model="qwen2.5:14b").bind_tools([x402_paid_web_extractor])

# Run invocation
query = "Scrape and extract story titles from https://news.ycombinator.com"
response = llm.invoke(query)

# Execute tool call requested by the model
for tool_call in response.tool_calls:
    if tool_call["name"] == "x402_paid_web_extractor":
        output = x402_paid_web_extractor.invoke(tool_call["args"])
        print("\n--- Agent Tool Output Received ---")
        print(output)