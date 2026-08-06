# 06 — Runtime data-flow overlay technique

Type: grilling · Status: pending · Blocked by: 02

## Question

How does FlowSight capture real data flowing through functions and overlay it on the static skeleton? The user wants to see actual parameter values and data moving (e.g., audio chunk → ASR → LLM → TTS in a live voice interaction). Decide the instrumentation approach (sys.settrace / sys.audit / import-hook monkey-patching / viztracer / a custom tracer), how the user drives a trace (run their app under FlowSight? point at a trace file?), and how captured calls+args map onto skeleton nodes. Depends on the primitives survey (02).
