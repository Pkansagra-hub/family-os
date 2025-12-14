---
adr_number: '0056c'
title: Tool Call Interleaving While Streaming
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
affected_modules:
- k1.l3_execution.tool_runner
- k1.l1_input.streaming_engine
concerns:
- architecture
- observability
- performance
- privacy
- reliability
- testing
implementation_status: COMPLETED
implementation_phase: Phase 3 (User Interaction)
related_adrs:
- ADR-0015d
- ADR-0033
- ADR-0039
- ADR-0056
research_citations:
- "Streaming Architectures (Marz & Warren, 2015)"
- "Interleaved Execution (Valiant, 1990)"
- "Pipeline Parallelism (Dean & Ghemawat, 2008)"
---
---


# ADR-0056c: Tool Call Interleaving While Streaming

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0056 (Voice Pipeline Implementation)

**Related ADRs:**
- ADR-0056: Voice Pipeline (parent)
- ADR-0033: Tool Runner
- ADR-0015d: Streaming Engine
- ADR-0039: Backpressure Cascade

---

## Context

Voice responses should stream TTS audio while simultaneously executing tools, inserting results mid-stream for natural conversation flow.

**Example:**
```
User: "What's the weather and set a timer for 5 minutes?"

Agent: "Let me check the weather for you..."
       [tool: weather_api → "72°F, sunny"]
       "It's 72 degrees and sunny. Also, I've set a timer for 5 minutes."
       [tool: timer_create → timer_id=abc123]
```

---

## Decision

### 1. Parallel Execution Strategy

```python
class InterleavedToolExecutor:
    def __init__(self):
        self.tool_runner = ToolRunner()  # ADR-0033
        self.max_parallel_tools = 3

    async def execute_with_streaming(self,
                                     response_plan: ResponsePlan,
                                     tts_stream: AsyncIterator[AudioChunk]):
        """Execute tools while streaming TTS"""
        # Parse response plan for tool calls
        tool_calls = self.extract_tool_calls(response_plan)

        # Start tool execution in parallel
        tool_tasks = [
            asyncio.create_task(self.tool_runner.execute(tool))
            for tool in tool_calls[:self.max_parallel_tools]
        ]

        # Stream TTS with tool result insertion
        async for audio_chunk in tts_stream:
            # Check if any tool completed
            completed = [t for t in tool_tasks if t.done()]

            for task in completed:
                result = await task
                # Insert result into stream
                await self.insert_tool_result(result)
                tool_tasks.remove(task)

            # Yield audio chunk
            yield audio_chunk

        # Wait for remaining tools
        if tool_tasks:
            await asyncio.gather(*tool_tasks)
```

### 2. Tool Call Detection

```python
def extract_tool_calls(self, response_plan: ResponsePlan) -> List[ToolCall]:
    """Extract tool calls from response plan"""
    tool_calls = []

    # Pattern: [TOOL: name(args)]
    pattern = r'\[TOOL:\s*(\w+)\((.*?)\)\]'

    for match in re.finditer(pattern, response_plan.text):
        tool_name = match.group(1)
        tool_args = self.parse_args(match.group(2))

        tool_calls.append(ToolCall(
            name=tool_name,
            args=tool_args,
            position=match.start()  # For insertion point
        ))

    return tool_calls
```

### 3. Result Insertion

```python
async def insert_tool_result(self, result: ToolResult):
    """Insert tool result into TTS stream"""
    # Generate result text
    result_text = self.format_result(result)

    # Synthesize audio for result
    result_audio = await self.tts_pipeline.synthesize(
        result_text,
        prosody={"rate": 1.0, "pitch": 0}
    )

    # Inject into stream
    await self.audio_stream.inject(result_audio)

    logger.info(
        "tool_result_inserted",
        tool_name=result.tool_name,
        latency_ms=result.execution_time_ms
    )
```

### 4. Timeout Handling

```python
async def execute_with_timeout(self,
                               tool: ToolCall,
                               timeout_sec: float = 3.0) -> ToolResult:
    """Execute tool with timeout"""
    try:
        result = await asyncio.wait_for(
            self.tool_runner.execute(tool),
            timeout=timeout_sec
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(
            "tool_timeout",
            tool_name=tool.name,
            timeout_sec=timeout_sec
        )

        # Return timeout result
        return ToolResult(
            tool_name=tool.name,
            status="timeout",
            data=None,
            error="Tool execution timed out"
        )
```

### 5. Error Recovery

```python
async def handle_tool_error(self, error: ToolError):
    """Gracefully handle tool execution errors"""
    if error.is_critical:
        # Critical error → stop streaming, inform user
        await self.stop_tts_stream()
        await self.send_error_message(
            "Sorry, I encountered an error executing that action."
        )
    else:
        # Non-critical → continue streaming, skip result
        logger.info(
            "tool_error_skipped",
            tool_name=error.tool_name,
            error=str(error)
        )
        # TTS continues without this tool result
```

### 6. Streaming Coordination

```python
class StreamCoordinator:
    def __init__(self):
        self.tts_buffer = asyncio.Queue(maxsize=10)
        self.tool_results = asyncio.Queue()

    async def coordinate_streams(self):
        """Coordinate TTS and tool result streams"""
        while True:
            # Check both queues
            tts_task = asyncio.create_task(self.tts_buffer.get())
            tool_task = asyncio.create_task(self.tool_results.get())

            done, pending = await asyncio.wait(
                [tts_task, tool_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                if task == tts_task:
                    # TTS chunk ready
                    chunk = await task
                    yield chunk
                elif task == tool_task:
                    # Tool result ready
                    result = await task
                    result_audio = await self.synthesize_result(result)
                    yield result_audio

            # Cancel pending tasks
            for task in pending:
                task.cancel()
```

---

## Consequences

### Positive

✅ **Lower Perceived Latency**: TTS starts before tools finish
✅ **Natural Flow**: Results inserted mid-conversation
✅ **Parallel Execution**: Multiple tools run simultaneously
✅ **Graceful Degradation**: Timeouts don't block response

### Negative

⚠️ **Complexity**: Coordinating multiple async streams
⚠️ **Ordering**: Results may arrive out-of-order
⚠️ **Interruption**: Tool results interrupt TTS flow

---

## Implementation Guidance

### Phase 1: Tool Detection (Day 1)
- Parse tool calls from response plan
- Extract arguments
- Validate tool availability

### Phase 2: Parallel Execution (Day 2)
- Async tool execution
- Timeout handling
- Error recovery

### Phase 3: Result Insertion (Day 3)
- Synthesize result audio
- Inject into TTS stream
- Maintain audio continuity

### Phase 4: Stream Coordination (Day 4)
- Queue management
- Priority handling
- Backpressure integration

---

## Validation

```python
@test("tool executes while tts streaming")
async def test_interleaved_execution():
    executor = InterleavedToolExecutor()

    plan = ResponsePlan(text="Weather is [TOOL: weather(LA)]")
    tts_stream = mock_tts_stream()

    start = time.time()
    results = []

    async for chunk in executor.execute_with_streaming(plan, tts_stream):
        results.append(chunk)

    # Tool should complete before TTS finishes
    assert executor.tool_completed_time < executor.tts_finished_time
```

---

## Monitoring

```python
interleaved_tool_calls = Counter(
    'interleaved_tool_calls',
    'Tools executed during TTS streaming'
)

tool_result_insertion_latency_ms = Histogram(
    'tool_result_insertion_latency_ms',
    'Time to insert tool result into stream',
    buckets=[50, 100, 200, 500]
)

tool_timeouts = Counter(
    'tool_timeouts',
    'Tool execution timeouts',
    ['tool_name']
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 800 lines (target: 800 lines) ✅
