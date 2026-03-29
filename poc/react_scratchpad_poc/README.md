# ReactLoopScratchpad PoC

Benchmark comparing **Naive ReAct** (append everything) vs **Smart ReAct** (managed scratchpad) across 8 scenarios.

## What This Proves

A ReAct loop with a managed scratchpad can run indefinitely, handle complex sub-agent hierarchies, respect budgets, and maintain perfect fact recall -- while a naive message-passing loop hits context limits, loses information, and fails on multi-step tasks.

## Quick Start

```bash
cd poc/react_scratchpad_poc
pip install -r requirements.txt
python demo.py --list                   # See all scenarios
python demo.py --scenarios 1 --mode smart  # Quick test
python demo.py                          # Full benchmark
```

## Architecture

```
Naive (Control)                    Smart (Innovation)
messages = [sys, user]             scratchpad = Scratchpad()
loop:                              loop:
  resp = llm(ALL messages)           context = scratchpad.to_llm_messages()
  execute tools                      resp = llm(context)  # bounded!
  messages.append(results)           execute tools
                                     extract_findings(results)
                                     compact_if_needed()
                                     track_budget()
```

## 8 Test Scenarios

| # | Name | What It Tests |
|---|------|--------------|
| 1 | Context Stress | 20 topics, 50 iterations -- naive runs out of context |
| 2 | Sub-Agent Spawn | 5 sub-agents with finding aggregation |
| 3 | Budget Inheritance | 10 tool calls shared across 3 sub-agents |
| 4 | Recovery | Handle tool failures with adaptive strategy |
| 5 | Deep Nesting | 4-level agent hierarchy |
| 6 | Parallel Agents | 3 independent sub-agents for travel planning |
| 7 | Budget Recovery | Unused budget returned from failed sub-agent |
| 8 | Fact Retention | 30 iterations, facts from iter 3 needed at iter 28 |

## Key Innovation: Structured Findings

Instead of stuffing raw tool output into message history:
```
Naive: messages.append("Tool weather_api result: {'city': 'Paris', 'temp_c': 22, 'condition': 'Partly Cloudy', 'humidity': 65, ...}")
```

The scratchpad extracts typed, queryable facts:
```
Smart: findings["paris_temperature"] = Finding(key="paris_temperature", value=22, type="weather")
```

These findings persist across compactions -- old messages get summarized, but facts never get lost.

## Output

- Rich terminal dashboard with color-coded comparison tables
- JSON results in `eval/results/` for programmatic analysis
- Per-scenario metrics: context size, token usage, findings count, compactions
- Context growth visualization: naive grows linearly, smart stays flat

## Configuration

LLM config loaded from `../chat_experience_poc/.env`:
- `GOOGLE_API_KEY` -- Gemini API key
- `GOOGLE_MODEL` -- Model name (default: gemini-2.5-flash)
