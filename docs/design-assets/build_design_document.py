"""
Assembles the final .docx from content_data.py + docx_engine.py.
"""

from pathlib import Path

from docx_engine import build_document
from content_data import SECTIONS

ASSETS_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(__file__).resolve().parents[1] / "MemSOC_Technical_Design_and_Architecture_Document_v2.docx"

COVER = {
    "title": "MemSOC",
    "subtitle": "Technical Design and Architecture Document",
    "meta_lines": [
        "Agentic SOC Alert Triage with a Persistent Memory Layer",
        "",
        "2026-09-03",
    ],
}

RUNNING_HEADER = "MemSOC -- Technical Design and Architecture Document"

if __name__ == "__main__":
    path = build_document(SECTIONS, ASSETS_DIR, OUT_PATH, COVER, RUNNING_HEADER)
    print(f"\nWrote {path}")
