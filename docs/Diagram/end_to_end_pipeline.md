# MemSOC End-to-End Pipeline

```mermaid
flowchart TD
    Dataset[NF-UNSW-NB15 dataset] --> Generator[Flow generator]
    Generator --> Capture[live_capture.py]
    Capture -->|HTTP POST /api/logs| Detection

    subgraph Docker Compose
        Detection[Detection API :8000\nLightGBM inference]
        Report[Report API :8001\nFastAPI report service]
        Dashboard[Dashboard :8080\nReact + Nginx]
        LogGeneration[log_generation\none-shot flow replay]
    end

    Detection -->|Prediction and alert metadata| Results[(LLMTriage/model_outputs/\nlive_results.jsonl)]
    Results -->|Read captured results| Report
    Report -->|Security-analysis request| Groq[Groq LLM API]
    Groq -->|Generated analysis| Report
    Report -->|Write report files| Reports[(LLMTriage/reports/)]
    Reports -->|GET /api/reports| Dashboard
    Analyst[SOC analyst] -->|View reports| Dashboard

    Generator -. Container-only, one-shot path .-> LogGeneration
    LogGeneration -. HTTP POST over Docker network .-> Detection
```
The standard operational path is Dataset → live_capture.py → Detection → live_results.jsonl → Report → Groq → reports/ → Dashboard. The log_generation service is a one-shot Docker Compose flow-replay service that sends generated flows directly to the Detection API and does not itself populate live_results.jsonl.
