# Deployment Options for the Remote Planner

The Warehouse AGV's remote planner (VLM + LLM) can be deployed in three configurations depending on your budget, latency requirements, and infrastructure availability.

## Option A: MacBook on Same WiFi (Default)

**Best for:** Development, testing, demos

### Setup
```bash
# On MacBook
brew install ollama
ollama serve  # Start Ollama daemon

# Pull models
ollama pull moondream       # MoondreamV2 VLM (~1.8GB)
ollama pull phi3:mini       # Phi-3 Mini LLM (~2.3GB)

# Start planner server
cd planner/
pip install -r requirements.txt
python server.py
```

### Configuration
On the Jetson Nano, edit `jetson/config.py`:
```python
PLANNER_HOST = "192.168.1.100"  # Your MacBook's WiFi IP
PLANNER_PORT = 8000
```

### Characteristics
| Metric | Value |
|--------|-------|
| Round-trip latency | 200-500ms (VLM) / 100-300ms (LLM only) |
| RAM usage | ~6GB on MacBook |
| Cost | Free |
| Reliability | Depends on WiFi + MacBook uptime |
| Max concurrent robots | 1 (maybe 2 with queuing) |

### Pros
- Zero cost
- Low latency on local WiFi
- Easy to iterate on prompts and models
- Full control over model selection

### Cons
- MacBook must be on and awake
- Tied to local WiFi range
- Single point of failure

---

## Option B: Dedicated Always-On Server

**Best for:** Production/permanent installations, multi-robot setups

### Hardware Options

| Option | Specs | Est. Cost | Notes |
|--------|-------|-----------|-------|
| NVIDIA Jetson Orin Nano | 8GB, 40 TOPS | ~$250 | Same form factor as Jetson Nano |
| Mini PC (Intel N100) | 16GB RAM, no GPU | ~$150 | CPU inference only, slower |
| Used desktop + GPU | GTX 1060+ / 6GB VRAM | ~$300-500 | Best performance/$$ |
| Raspberry Pi 5 8GB | ARM, CPU only | ~$80 | Very slow inference, not recommended |

### Recommended: Used desktop with GTX 1060/1070

```bash
# Ubuntu Server 22.04 setup
# Install NVIDIA drivers
sudo apt install nvidia-driver-535

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull moondream
ollama pull phi3:mini

# Start planner as a systemd service
sudo cp warehouse-agv-planner.service /etc/systemd/system/
sudo systemctl enable warehouse-agv-planner
sudo systemctl start warehouse-agv-planner
```

### Systemd Service File
Save as `/etc/systemd/system/warehouse-agv-planner.service`:
```ini
[Unit]
Description=Warehouse AGV Planner Server
After=network.target ollama.service

[Service]
Type=simple
User=agv
WorkingDirectory=/home/agv/warehouse-agv/planner
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Network Configuration
```python
# jetson/config.py
PLANNER_HOST = "192.168.1.50"  # Static IP for the server
PLANNER_PORT = 8000
```

For multi-robot support, add a load balancer or run multiple server instances.

### Characteristics
| Metric | Value |
|--------|-------|
| Round-trip latency | 100-400ms (with GPU) / 500-2000ms (CPU only) |
| RAM usage | 8-16GB |
| Cost | $150-500 one-time |
| Reliability | High (always-on, auto-restart) |
| Max concurrent robots | 2-5 (with GPU) |

### Pros
- Always available
- Can serve multiple robots
- Auto-restart on failure
- Better suited for production

### Cons
- Upfront hardware cost
- Needs physical space and power
- Maintenance overhead

---

## Option C: Cloud API

**Best for:** Scalability, no local hardware, rapid prototyping with large models

### Provider Options

| Provider | Model | Free Tier | Paid Cost | Latency |
|----------|-------|-----------|-----------|---------|
| Groq | Llama 3.1 8B | 30 req/min | $0.05/1M tokens | ~100ms |
| Together.ai | Llama 3.1 8B | $5 free credit | $0.18/1M tokens | ~200ms |
| Together.ai | LLaVA 1.6 (VLM) | included | $0.20/1M tokens | ~300ms |
| Fireworks.ai | Phi-3 | Free tier | $0.10/1M tokens | ~150ms |
| Replicate | Moondream | Free for small usage | $0.0002/run | ~500ms |

### Recommended: Groq (LLM) + Replicate (VLM)

#### Modified `vlm_service.py` for Replicate:
```python
import replicate

class VLMServiceCloud:
    def __init__(self):
        self.model = "vikhyatk/moondream2:latest"
    
    def describe(self, image_bytes: bytes, prompt: str) -> str:
        import base64
        image_b64 = base64.b64encode(image_bytes).decode()
        output = replicate.run(
            self.model,
            input={
                "image": f"data:image/jpeg;base64,{image_b64}",
                "question": prompt
            }
        )
        return "".join(output)
```

#### Modified `llm_service.py` for Groq:
```python
from groq import Groq

class LLMServiceCloud:
    def __init__(self):
        self.client = Groq()  # Uses GROQ_API_KEY env var
        self.model = "llama-3.1-8b-instant"
    
    def plan(self, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=500
        )
        return response.choices[0].message.content
```

#### Environment Variables:
```bash
export GROQ_API_KEY="gsk_..."
export REPLICATE_API_TOKEN="r8_..."
```

### Characteristics
| Metric | Value |
|--------|-------|
| Round-trip latency | 200-800ms (depends on provider + internet) |
| RAM usage | Minimal (API calls only) |
| Cost | $0-20/month for hobby use |
| Reliability | High (cloud providers have 99.9%+ uptime) |
| Max concurrent robots | Unlimited (rate limits apply) |

### Pros
- No local hardware needed
- Access to larger/better models
- Scales to many robots
- Pay only for what you use

### Cons
- Requires internet connection
- Higher latency than local
- Cost scales with usage
- Privacy concerns (images leave your network)
- Rate limits on free tiers

---

## Comparison Summary

| Factor | A: MacBook | B: Dedicated Server | C: Cloud API |
|--------|-----------|--------------------:|-------------:|
| Setup time | 5 minutes | 1-2 hours | 30 minutes |
| Cost | Free | $150-500 once | $0-20/month |
| Latency | 200-500ms | 100-400ms | 200-800ms |
| Reliability | Low | High | High |
| Scalability | 1 robot | 2-5 robots | Unlimited |
| Privacy | Full | Full | Images leave network |
| Internet required | No | No | Yes |

## Switching Between Options

The planner server interface (`/describe`, `/plan`, `/goal`, `/help`) remains the same regardless of deployment option. Only the `vlm_service.py` and `llm_service.py` implementations change.

To switch:
1. Replace `vlm_service.py` and `llm_service.py` with the cloud versions
2. Set API keys as environment variables
3. Update `jetson/config.py` with the new planner URL
4. Restart the planner server

The Jetson Nano client code requires **zero changes** — it always talks to the same REST API.
