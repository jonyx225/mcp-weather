# 🦙 Llama3 MCP Weather Assistant

_Local AI Weather Chat with Real-Time NWS Data_

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org) [![MCP](https://img.shields.io/badge/MCP-v0.1-green)](https://modelcontextprotocol.io) [![Llama3](https://img.shields.io/badge/Llama3-8B%20Local-llama)](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)

**Offline AI that fetches LIVE US weather alerts & forecasts using Llama3 + MCP!** No API keys, no cloud, 100% private.

---

## 🚀 What It Does

| **Feature**         | **Description**                                         | **Example**                                                |
| ------------------- | ------------------------------------------------------- | ---------------------------------------------------------- |
| **Weather Alerts**  | Get **active severe weather warnings** for any US state | `Get alerts for CA` → "Flash Flood Warning in Los Angeles" |
| **5-Day Forecast**  | Detailed forecast by **GPS coordinates**                | `Forecast for NYC` → "Monday: 72°F, Sunny, 10mph winds"    |
| **Local Llama3 AI** | **Smart routing**—Llama3 decides which tool to use      | `Is it safe to drive in Texas?` → Auto-fetches alerts      |
| **Real-Time Data**  | Powered by **NOAA/NWS API** (free, official US weather) | Always current, no rate limits                             |

**Perfect for:** Emergency alerts, travel planning, local weather checks—**all offline AI-powered**!

---

## 📦 Quick Setup (5 Minutes)

### Prerequisites

- Python 3.8+
- 8GB+ RAM (for Llama3 8B)
- [uv](https://astral.sh/uv) (fast package manager)

### Step 1: Clone & Install

```bash
# Clone this repo
git clone <your-repo>
cd mcp-weather

# Install dependencies (30s)
uv sync
```

### Step 2: Run the client

```bash
uv run client-llama3.py ../mcp-server-weather/server.py
```

## Example

```bash
🦙 LOCAL Llama3 MCP Client Started!

Query: Get weather alerts for California
---
Event: Flash Flood Warning
Area: Los Angeles County
Severity: Moderate
Description: Heavy rain expected until 6PM
Instructions: Avoid low-lying areas

Query: Forecast for New York City
---
Monday:
Temperature: 68°F
Wind: 8mph SW
Forecast: Partly cloudy with 20% chance of rain
---
Tuesday:
Temperature: 72°F
...
```
