# Universal Collectibles Vault (`collectible-vault`)

[![Docker](https://img.shields.io/badge/Docker-Supported-blue?logo=docker)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)](https://fastapi.tiangolo.com/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Enabled-purple)](https://github.com/jlowin/fastmcp)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

An open-source, containerized, self-hosted web application for collectors to manage **comics, Funko Pops, action figures, and trading cards**. Replaces subscription services (CLZ, Funko tracking apps) with zero-friction camera scanning (UPC + local vision AI), automatic eBay sold-comps valuation, and FastMCP integration for natural-language AI assistants.

---

## 🏛️ System Architecture

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                            User Mobile / Web UI                         │
 │               (HTML5 Camera Scanner / Vision Upload / Dashboard)         │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ REST API / Base64 Image
 ┌────────────────────────────────────▼────────────────────────────────────┐
 │                       FastAPI App Core (Container 1)                    │
 ├────────────────────────────────────┬────────────────────────────────────┤
 │  • Barcode/UPC Intake Engine       │  • Valuation Refresh Engine        │
 │  • Pre-flight Metadata Form        │  • Analytics & Dashboard Stats API │
 └──────────────┬─────────────────────┴─────────────┬──────────────────────┘
                │ SQLite Hybrid Schema              │ Base64 Vision Payload
 ┌──────────────▼─────────────┐      ┌──────────────▼──────────────────────┐
 │    SQLite Hybrid Vault DB  │      │ Ollama Vision LLM (Container 3)     │
 │  (JSON Dynamic Metadata)   │      │ (qwen2-vl / llava model endpoint)   │
 └──────────────▲─────────────┘      └─────────────────────────────────────┘
                │ Direct SQLite access / ORM
 ┌──────────────┴─────────────┐
 │  FastMCP Server Daemon     │ <=========>  Claude Desktop / Ollama Agent
 │  (Natural Language AI)     │              "Show top comic value gains"
 └────────────────────────────┘
```

---

## 🚀 Key Features

1. **Frictionless "Snap & Add" Intake:**
   - **Path A (UPC Barcode):** Decode box/cover barcodes with instant pre-populated metadata lookup.
   - **Path B (Vision AI LLM):** Upload photos directly to a local vision LLM (Ollama `qwen2-vl` or `llava`) to extract Title, Issue #, Publisher, Era, and estimated condition.
   - **Pre-flight Confirmation UI:** Review auto-populated metadata and AI confidence score before saving.

2. **Universal Dynamic Hybrid Schema:**
   - Universal fields across all item types (`id`, `title`, `category`, `purchase_price`, `current_market_value`, `condition_grade`, `notes`).
   - Dynamic `metadata_json` field for category-specific tags (issue number, variant, box number, card set, grading service).

3. **Live Market Valuation Engine:**
   - Sold-comps algorithm simulating completed market listings to track true Fair Market Value (FMV).
   - Keeps historical valuation trend points to plot financial gains/losses over time with interactive Chart.js line graphs.

4. **FastMCP Natural Language AI Agent Server:**
   - Exposes vault tools (`get_vault_summary`, `add_item`, `query_item_market_value`, `list_top_collectibles`, `refresh_vault_valuations`) to Claude Desktop or Ollama agents.

---

## 🐳 Quickstart Deployment with Docker Compose

### Prerequisites
- Docker & Docker Compose installed on Linux / Proxmox VM.

### 1. Clone & Launch Stack
```bash
git clone https://github.com/your-username/collectible-vault.git
cd collectible-vault

docker-compose up -d
```

### 2. Access Web Dashboard
Open your web browser and navigate to:
```
http://localhost:8000
```
Or use your Proxmox VM IP: `http://<PROXMOX_SERVER_IP>:8000`

### 3. Enable Vision LLM Model (Optional)
Pull the vision LLM into the Ollama container:
```bash
docker exec -it collectible-vault-ollama ollama pull qwen2-vl
```

---

## 🤖 FastMCP Server Setup for AI Assistants

### Claude Desktop Integration (`claude_desktop_config.json`)
Add the following to your Claude Desktop config file:

```json
{
  "mcpServers": {
    "collectible-vault": {
      "command": "python",
      "args": [
        "/path/to/collectible-vault/mcp_server.py"
      ],
      "env": {
        "DATABASE_URL": "sqlite:////path/to/collectible-vault/vault.db"
      }
    }
  }
}
```

Now ask Claude:
> *"What's the total value of my comic book vault?"*  
> *"Add a 1st Edition Charizard card bought for $400 with current market value $1,850."*

---

## 🛠️ REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/items` | List collectibles (filters: `category`, `search`, `sort_by`) |
| `POST` | `/api/items` | Save new item to vault |
| `GET` | `/api/items/{id}` | Get item detail & valuation timeline |
| `DELETE` | `/api/items/{id}` | Delete item from vault |
| `POST` | `/api/intake/vision` | Upload photo for Ollama Vision LLM parsing |
| `POST` | `/api/intake/barcode` | Lookup UPC barcode metadata |
| `POST` | `/api/valuation/refresh` | Trigger live eBay sold comps refresh |
| `GET` | `/api/dashboard/stats` | Get aggregated portfolio stats & top items |

---

## 📄 License
Released under the MIT License.
