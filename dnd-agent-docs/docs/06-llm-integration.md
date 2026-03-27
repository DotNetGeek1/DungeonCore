# LLM Integration Strategy

## Current Requirement

Model access is local-first using LM Studio.

## Future Requirement

The system must later support Azure AI Foundry without changing the rest of the architecture in painful ways.

## Core Principle

Treat model providers as interchangeable backends behind a stable adapter boundary.

## Provider Abstraction

The runtime should depend on a provider-neutral contract.

### Required capabilities
- chat or completion-style generation
- configurable temperature and token limits
- structured response support where possible
- timeout and retry handling
- usage and latency metadata

## LM Studio Integration Notes

Use LM Studio for:
- local prototyping
- low-cost development loops
- model experimentation
- early multi-agent testing

Potential challenges:
- inconsistent structured output depending on model
- local hardware throughput constraints
- concurrency limits under multiple active agents

### Practical implication
The runtime must be resilient to malformed outputs and slower local inference.

## Azure AI Foundry Integration Notes

Use later for:
- hosted model scale
- central management
- enterprise controls
- broader model options
- team-accessible environments

## Recommended Provider Config Model

```python
from pydantic import BaseModel
from typing import Literal, Optional, Dict, Any

class ProviderConfig(BaseModel):
    provider: Literal["lmstudio", "azure_ai_foundry"]
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    model_name: str
    default_temperature: float = 0.4
    extra: Dict[str, Any] = {}
```

## Routing Strategy

Allow per-agent model assignment.

Examples:
- DM agent on a stronger narrative model
- player agents on cheaper/faster local models
- summarization on a smaller utility model

## Failure Handling

Required handling:
- timeout protection
- invalid JSON retries
- provider unavailable fallback handling
- structured logging of failures

## Structured Output Strategy

Never trust raw model text blindly.

Preferred order:
1. provider-native structured response mode if supported
2. strict JSON prompt contract
3. parser + schema validator
4. retry once or twice with repair prompt
5. fallback action if still invalid

## Observability

For every provider call, log:
- provider
- model
- latency
- response validity
- retry count
- approximate token usage if available

## Security / Config Notes

Keep credentials out of code and docs.
Use environment variables and Docker secrets or equivalent later.

## Docker Considerations

The agent runtime should reach model providers via environment-driven endpoints.

Example env shape:

```env
MODEL_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://lmstudio:1234
AZURE_AI_FOUNDRY_ENDPOINT=
AZURE_AI_FOUNDRY_API_KEY=
DEFAULT_MODEL_NAME=your-default-model
```
