"""MemSOC -- memory-augmented LLM alert triage for a SOC.

Layers (see PROJECT_BRIEF.md section 4):

    logstream   Layer 1  deterministic NetFlow replay
    detection   Layer 2  frozen LightGBM classifier + SHAP
    memory      Layer 3  case store (the research variable)
    triage      Layer 4  LLM triage and report generation
    api                  every HTTP endpoint in the system
"""

__version__ = "1.0.0"
