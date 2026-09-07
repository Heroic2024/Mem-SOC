"""
Generates the architecture diagrams for the MemSOC Technical Design and
Architecture Document. Monochrome, academic style: black text and
borders throughout, a single neutral fill differentiated only by
subsystem grouping (not by build status), and dashed borders reserved
for data sources that are external to the system's own processing
(the LLM API, the evaluation oracle).
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from pathlib import Path

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Neutral, monochrome style. "kind" now selects a subsystem grouping
# shade, not a build-status color.
# ---------------------------------------------------------------------
FILL = {
    "layer1": "#f2f2f2",
    "layer2": "#e6e6e6",
    "layer3": "#eeeeee",
    "layer4a": "#f5f5f5",
    "layer4b": "#ececec",
    "external": "#ffffff",
    "plain": "#f7f7f7",
}
BLACK = "#000000"


def new_fig(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, label, kind="plain", fontsize=8.3, dashed=False):
    fill = FILL.get(kind, FILL["plain"])
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.15,rounding_size=1.0",
        linewidth=1.2, edgecolor=BLACK, facecolor=fill,
        linestyle="dashed" if dashed else "solid",
    ))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=fontsize, color=BLACK, wrap=True, linespacing=1.35)


def diamond(ax, x, y, w, h, label, fontsize=8.0):
    cx, cy = x + w / 2, y + h / 2
    pts = [(cx, y + h), (x + w, cy), (cx, y), (x, cy)]
    ax.add_patch(plt.Polygon(pts, closed=True, edgecolor=BLACK,
                              facecolor="#ffffff", linewidth=1.2))
    ax.text(cx, cy, label, ha="center", va="center", fontsize=fontsize, wrap=True)


def arrow(ax, start, end, label=None, rad=0.0, dashed=False, fontsize=7.2):
    a = FancyArrowPatch(
        start, end, arrowstyle="-|>", color=BLACK, linewidth=1.1,
        connectionstyle=f"arc3,rad={rad}", mutation_scale=12,
        linestyle="dashed" if dashed else "solid",
    )
    ax.add_patch(a)
    if label:
        mx = (start[0] + end[0]) / 2 + (0 if rad == 0 else rad * 10)
        my = (start[1] + end[1]) / 2
        ax.text(mx, my, label, fontsize=fontsize, color=BLACK, ha="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#999999", alpha=0.95))


def zone_label(ax, x, y, text, fontsize=10):
    ax.text(x, y, text, fontsize=fontsize, fontweight="bold", color=BLACK)


def save(fig, name):
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {path}")


# =======================================================================
# Figure -- Overall System Architecture (simple, 4-layer)
# =======================================================================
def fig_01():
    fig, ax = new_fig(11, 4.2)
    labels = [
        "Layer 1\nData Stream",
        "Layer 2\nDetection",
        "Layer 3\nMemory",
        "Layer 4\nLLM Triage and Reporting",
    ]
    kinds = ["layer1", "layer2", "layer3", "layer4a"]
    xs = [3, 27, 51, 75]
    for x, label, kind in zip(xs, labels, kinds):
        box(ax, x, 40, 20, 20, label, kind=kind, fontsize=9)
    for i in range(3):
        arrow(ax, (xs[i] + 20, 50), (xs[i + 1], 50))
    arrow(ax, (xs[3] + 10, 40), (xs[2] + 10, 40), label="write-back", rad=-0.35)
    ax.text(50, 15, "Data flows left to right through the four layers; Layer 4 writes triaged\n"
                     "cases back into Layer 3, which supplies precedent for later alerts.",
            ha="center", fontsize=8, color=BLACK)
    save(fig, "fig01_overall_architecture.png")


# =======================================================================
# Figure -- Complete System Architecture
# =======================================================================
def fig_02():
    fig, ax = new_fig(20, 15)

    zone_label(ax, 2, 97, "DATA GENERATION  (Layer 1)")
    box(ax, 2, 88, 18, 7, "NF-UNSW-NB15-v3.csv\n2.36M flows", "external", 7.5)
    box(ax, 22, 88, 18, 7, "log_generation/\nnfv3_log_generator.py\nrun_pipeline.py", "layer1", 7.3)
    box(ax, 44, 88, 16, 7, "generated_logs.jsonl\n48 features, no label", "layer1", 7.3)
    box(ax, 62, 88, 16, 7, "ground_truth.csv\nuid,label,attack", "external", 7.3, dashed=True)
    arrow(ax, (20, 91.5), (22, 91.5))
    arrow(ax, (40, 91.5), (44, 91.5))
    arrow(ax, (40, 90), (62, 90), rad=-0.15)

    zone_label(ax, 2, 82, "DETECTION  (Layer 2)")
    box(ax, 22, 70, 20, 9, "Detection API :8000\nfinal_ml_model_v1\nLightGBM binary + multiclass\n+ SHAP + AlertGenerator", "layer2", 7.3)
    arrow(ax, (50, 88), (32, 79), label="POST /api/logs (replay)")

    box(ax, 46, 70, 18, 9, "live_capture.py\n(LLMTriage/)", "layer4a", 7.3)
    arrow(ax, (46, 74), (42, 74), label="POST /api/logs")
    box(ax, 68, 70, 18, 9, "live_results.jsonl\ndetector output\n(status/binary/multiclass/\nalert incl. SHAP)", "layer4a", 7.0)
    arrow(ax, (64, 74), (68, 74))

    zone_label(ax, 2, 63, "AGGREGATE REPORTING PIPELINE  (Layer 4a)")
    box(ax, 2, 52, 16, 8, "stats_engine.py\nstatistics", "layer4a", 7.0)
    box(ax, 20, 52, 16, 8, "report_prompt.py\n+ llm_client.py", "layer4a", 7.0)
    box(ax, 38, 52, 14, 8, "LLM API\n(chat completions)", "external", 7.0, dashed=True)
    box(ax, 54, 52, 16, 8, "generate_report.py\nreports/*.json/.md", "layer4a", 7.0)
    box(ax, 72, 52, 12, 8, "report_server.py\n:8001", "layer4a", 6.8)
    box(ax, 86, 52, 12, 8, "React\nDashboard", "layer4a", 6.8)
    arrow(ax, (77, 70), (10, 43), rad=-0.15)
    arrow(ax, (44, 88), (10, 39), rad=0.35)
    for a, b in [(18, 20), (36, 38), (52, 54), (70, 72), (84, 86)]:
        arrow(ax, (a, 56), (b, 56))

    zone_label(ax, 2, 46, "PER-ALERT TRIAGE PIPELINE  (Layer 4b)")
    box(ax, 2, 35, 16, 8, "triage_runner.py\ndedupe + join features", "layer4b", 6.8)
    box(ax, 20, 35, 16, 8, "triage_prompt.py\n+ llm_client.py", "layer4b", 6.8)
    box(ax, 38, 35, 14, 8, "LLM API\n(chat completions)", "external", 7.0, dashed=True)
    box(ax, 54, 35, 16, 8, "triage_verdicts.jsonl\nverdict, category,\nconfidence, rationale", "layer4b", 6.6)
    box(ax, 72, 35, 12, 8, "score_verdicts.py", "layer4b", 6.8)
    box(ax, 86, 35, 12, 8, "Metrics vs\nground truth", "layer4b", 6.5)
    for a, b in [(18, 20), (36, 38), (52, 54), (70, 72), (84, 86)]:
        arrow(ax, (a, 39), (b, 39))
    arrow(ax, (70, 88), (78, 43), rad=0.15, label="ground_truth.csv\n(scoring only)")

    zone_label(ax, 2, 29, "MEMORY LAYER  (Layer 3)")
    box(ax, 2, 18, 18, 8, "Case Ranker\n(memory/case_ranker/)\nselects and compacts cases", "layer3", 6.8)
    box(ax, 22, 18, 16, 8, "CaseRenderer\n+ EmbeddingFunction", "layer3", 6.8)
    box(ax, 40, 18, 16, 8, "MemoryStore\n(ChromaDB)", "layer3", 6.8)
    box(ax, 58, 18, 18, 8, "Retriever / Writer\nprecedent injection +\nwrite-back", "layer3", 6.6)
    arrow(ax, (10, 35), (10, 26), label="live_results.jsonl")
    arrow(ax, (20, 22), (22, 22))
    arrow(ax, (38, 22), (40, 22))
    arrow(ax, (56, 22), (58, 22))
    arrow(ax, (67, 35), (67, 26), rad=0.2, label="retrieval and write-back")

    zone_label(ax, 2, 12, "DEPLOYMENT")
    box(ax, 2, 2, 30, 8, "Docker Compose\nDetection API service published;\nother services run on host", "external", 6.8)

    save(fig, "fig02_complete_architecture.png")


# =======================================================================
# Figure -- Component / Module Architecture
# =======================================================================
def fig_04():
    fig, ax = new_fig(16, 12)

    def group(x, y, w, h, title, kind, files, fontsize=6.6):
        fill = FILL.get(kind, FILL["plain"])
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1",
                                     linewidth=1.2, edgecolor=BLACK, facecolor=fill))
        ax.text(x + 1.5, y + h - 3, title, fontsize=8.5, fontweight="bold")
        for i, f in enumerate(files):
            ax.text(x + 2, y + h - 7 - i * 3.3, f"- {f}", fontsize=fontsize, va="top")

    group(1, 74, 30, 22, "Layer 1 -- log_generation/", "layer1", [
        "nfv3_log_generator.py", "replay_to_api.py", "stream_to_api.py",
        "run_pipeline.py", "test_pipeline.py",
    ])
    group(34, 74, 30, 22, "Layer 2 -- final_ml_model_v1/", "layer2", [
        "src/api/server.py", "src/inference/inference_pipeline.py",
        "src/models/train_binary.py / train_multiclass.py",
        "src/explain/shap_explainer.py", "src/alerts/alert_generator.py",
    ])
    group(67, 74, 32, 22, "Root infrastructure", "external", [
        "paths.py (path resolution)", "Dockerfile / docker-compose.yml",
        "requirements-runtime.txt",
    ])

    group(1, 42, 47, 29, "Layer 4a -- LLMTriage/ (aggregate reporting)", "layer4a", [
        "live_capture.py", "stats_engine.py", "report_prompt.py",
        "llm_client.py", "generate_report.py", "report_server.py",
        "dashboard/ (React + Vite)",
    ])
    group(50, 42, 49, 29, "Layer 4b -- LLMTriage/ (per-alert triage)", "layer4b", [
        "triage_prompt.py", "triage_runner.py", "score_verdicts.py",
        "config.py (shared)", "llm_client.py (shared, extended)",
    ])

    group(1, 15, 47, 24, "Layer 3 -- memory/", "layer3", [
        "docs/memory-layer/*.md (design specification)",
        "SCHEMA_DESIGN.md, SETUP_PLAN.md",
        "case_ranker/build_memory_input.py",
        "case_ranker/risk.py, token_estimator.py",
        "EmbeddingFunction, MemoryStore, Retriever, Writer",
    ])
    group(50, 15, 49, 24, "Shared data artifacts", "external", [
        "generated_logs.jsonl / ground_truth.csv",
        "live_results.jsonl",
        "reports/*.json, *.md",
        "triage_verdicts.jsonl",
        "memory_input_*.json/.txt",
    ])
    save(fig, "fig04_component_architecture.png")


# =======================================================================
# Figure -- End-to-End Data Flow (file-artifact centric)
# =======================================================================
def fig_05():
    fig, ax = new_fig(16, 10)
    steps = [
        ("NF-UNSW-NB15-v3.csv", "external"),
        ("generated_logs.jsonl\n+ ground_truth.csv", "layer1"),
        ("live_results.jsonl", "layer4a"),
    ]
    x = 2
    for label, kind in steps:
        box(ax, x, 78, 20, 14, label, kind, 7.5)
        if x > 2:
            arrow(ax, (x - 6, 85), (x, 85))
        x += 26

    box(ax, 4, 50, 22, 14, "reports/\n*.json + *.md", "layer4a", 7.3)
    box(ax, 30, 50, 22, 14, "triage_verdicts.jsonl", "layer4b", 7.3)
    box(ax, 58, 50, 22, 14, "memory_input_*.json/.txt", "layer3", 7.0)
    arrow(ax, (14, 78), (14, 64), rad=0.2)
    arrow(ax, (54, 78), (40, 64), rad=-0.15)
    arrow(ax, (54, 78), (68, 64), rad=0.15)

    box(ax, 4, 26, 22, 14, "Dashboard\n(rendered pages)", "layer4a", 7.3)
    box(ax, 30, 26, 22, 14, "Metrics vs ground truth\n(scoring output)", "layer4b", 7.3)
    box(ax, 58, 26, 22, 14, "Embedding vector in\nMemoryStore", "layer3", 6.8)
    arrow(ax, (15, 50), (15, 40))
    arrow(ax, (41, 50), (41, 40))
    arrow(ax, (69, 50), (69, 40))

    ax.text(50, 12, "ground_truth.csv joins only into the scoring step below -- never into a prompt.",
            ha="center", fontsize=8, color=BLACK)
    arrow(ax, (12, 78), (36, 40), rad=-0.3, label="ground_truth.csv (scoring only)")
    save(fig, "fig05_end_to_end_data_flow.png")


# =======================================================================
# Figure -- Detection Pipeline
# =======================================================================
def fig_06():
    fig, ax = new_fig(8, 13)
    y = 92
    box(ax, 20, y, 60, 8, "Incoming JSON flow record", "external", 8)
    y -= 12; arrow(ax, (50, y + 12), (50, y + 8))
    box(ax, 20, y, 60, 8, "validate_input()\nall 48 features present?", "layer2", 7.5)
    y -= 12; arrow(ax, (50, y + 12), (50, y + 8))
    box(ax, 20, y, 60, 8, "prepare_dataframe()\ncoerce numeric, reject NaN", "layer2", 7.5)
    y -= 12; arrow(ax, (50, y + 12), (50, y + 8))
    box(ax, 20, y, 60, 8, "Binary LightGBM", "layer2", 8)
    y -= 12
    diamond(ax, 32, y, 36, 9, "Attack?")
    arrow(ax, (50, y), (50, y - 3))
    ax.text(15, y + 4.5, "Benign", fontsize=7.5, color=BLACK)
    arrow(ax, (32, y + 4.5), (10, y + 4.5))
    box(ax, 0, y - 6, 22, 8, "status: benign\n(stop)", "external", 6.8)
    y -= 12
    box(ax, 20, y, 60, 8, "Multiclass LightGBM\n9-category prediction", "layer2", 7.5)
    y -= 12; arrow(ax, (50, y + 12), (50, y + 8))
    box(ax, 20, y, 60, 8, "SHAPExplainer.explain()\ntop-10 features, deterministic order", "layer2", 7.3)
    y -= 12; arrow(ax, (50, y + 12), (50, y + 8))
    box(ax, 20, y, 60, 8, "AlertGenerator.generate()\nattack, confidence, ports,\nprotocol, shap_explanation", "layer2", 7.3)
    y -= 14; arrow(ax, (50, y + 14), (50, y + 8))
    box(ax, 15, y, 70, 8, "Alert JSON returned in the /api/logs response\n(this is what live_results.jsonl captures)", "layer4a", 7.2)
    save(fig, "fig06_detection_pipeline.png")


# =======================================================================
# Figure -- Per-Alert Triage Pipeline
# =======================================================================
def fig_11():
    fig, ax = new_fig(18, 13)
    zone_label(ax, 2, 96, "DATA GENERATION AND DETECTION  (Layers 1 and 2)")
    box(ax, 2, 84, 20, 9, "generated_logs.jsonl\n48 feature values\nno label", "layer1", 7.0)
    box(ax, 24, 84, 20, 9, "live_capture.py", "layer4a", 7.0)
    box(ax, 46, 84, 20, 9, "Detection API :8000", "layer2", 7.0)
    box(ax, 68, 84, 22, 9, "live_results.jsonl\ndetector output + SHAP\nno feature values", "layer4a", 6.8)
    arrow(ax, (24, 88), (24, 88))
    arrow(ax, (44, 88.5), (46, 88.5))
    arrow(ax, (66, 88.5), (68, 88.5))

    zone_label(ax, 2, 76, "TRIAGE PROCESSING")
    box(ax, 2, 62, 20, 10, "Load status==attack alerts\ndedupe by uid", "layer4b", 6.8)
    box(ax, 24, 62, 20, 10, "Join feature values\nfrom generated_logs.jsonl\n(SHAP needs the values\nit attributes to)", "layer4b", 6.6)
    diamond(ax, 47, 62, 20, 10, "uid already in\ntriage_verdicts.jsonl?")
    box(ax, 70, 74, 20, 8, "Skip -- already\ntriaged", "layer4b", 6.8)
    arrow(ax, (12, 84), (12, 72))
    arrow(ax, (22, 67), (24, 67))
    arrow(ax, (44, 67), (47, 67))
    arrow(ax, (67, 67), (80, 74), label="yes")

    box(ax, 24, 44, 22, 10, "triage_prompt.render()\ndetector label presented\nas a hypothesis", "layer4b", 6.6)
    box(ax, 50, 44, 20, 10, "llm_client.call_groq()\ntemperature 0\none alert per call", "layer4b", 6.8)
    box(ax, 74, 44, 22, 10, "parse_llm_response()\nvalidate closed vocabulary", "layer4b", 6.6)
    arrow(ax, (57, 62), (35, 54), label="no")
    arrow(ax, (46, 49), (50, 49))
    arrow(ax, (70, 49), (74, 49))

    box(ax, 40, 26, 34, 10, "triage_verdicts.jsonl\nverdict, attack_category, confidence,\nrationale_summary, precedent_used", "layer4b", 6.6)
    arrow(ax, (85, 44), (60, 36), rad=0.2)

    zone_label(ax, 2, 20, "EVALUATION")
    box(ax, 2, 6, 20, 10, "ground_truth.csv\n(evaluation oracle)", "external", 6.8, dashed=True)
    box(ax, 26, 6, 22, 10, "score_verdicts.py\njoin on uid", "layer4b", 6.8)
    box(ax, 52, 6, 44, 10, "Metrics: precision, recall, F1,\ncategory accuracy, agreement\nwith the detector", "layer4b", 6.6)
    arrow(ax, (55, 26), (37, 16), rad=-0.2)
    arrow(ax, (22, 11), (26, 11))
    arrow(ax, (48, 11), (52, 11))
    ax.text(2, 1.5, "No connection joins ground_truth.csv into triage processing above -- enforced by file separation.",
            fontsize=7.5, color=BLACK)

    arrow(ax, (24, 49), (10, 44), rad=0.3, label="retrieval of precedent\n(memory layer)")
    arrow(ax, (85, 44), (95, 30), rad=0.3, label="write-back\n(memory layer)")
    save(fig, "fig11_per_alert_triage_pipeline.png")


# =======================================================================
# Figure -- Per-Alert Triage Activity Diagram (resume/skip logic)
# =======================================================================
def fig_12():
    fig, ax = new_fig(15, 16)
    ax.set_xlim(-40, 100)

    box(ax, 35, 94, 30, 5, "Start", "external", 8)
    arrow(ax, (50, 94), (50, 90))

    box(ax, 25, 80, 50, 9, "Load live_results.jsonl, filter attacks,\ndedupe by uid, join feature values", "layer4b", 7.2)
    arrow(ax, (50, 80), (50, 75))

    box(ax, 25, 66, 50, 8, "Read existing triage_verdicts.jsonl", "layer4b", 7.2)
    arrow(ax, (50, 66), (50, 61))

    diamond(ax, 30, 49, 40, 11, "More alerts\nto process?")
    arrow(ax, (30, 54.5), (12, 54.5), label="yes")

    box(ax, 25, 30, 50, 8, "Run score_verdicts.py", "layer4b", 7.2)
    arrow(ax, (50, 49), (50, 38), label="no")
    arrow(ax, (50, 30), (50, 24))

    box(ax, 30, 14, 40, 6, "Stop", "external", 8)

    diamond(ax, 0, 49, 24, 11, "uid already in\nverdicts file?")
    arrow(ax, (12, 49), (12, 40), label="no")
    arrow(ax, (0, 54.5), (-13, 70), rad=0.35, label="yes -- skip")
    arrow(ax, (-13, 70), (25, 62), rad=0.3)

    box(ax, 0, 26, 24, 9, "Render prompt, call the\nLLM, validate response", "layer4b", 6.8)
    arrow(ax, (12, 40), (12, 35))

    diamond(ax, 0, 12, 24, 10, "Response valid\nJSON + vocabulary?")
    arrow(ax, (12, 26), (12, 22))

    box(ax, -32, 12, 24, 8, "Append verdict to\ntriage_verdicts.jsonl", "layer4b", 6.8)
    arrow(ax, (0, 17), (-8, 17), label="yes")
    arrow(ax, (-20, 20), (-20, 55), rad=0.3)
    arrow(ax, (-20, 55), (25, 51), rad=0.2, label="loop to next alert")

    box(ax, -32, -2, 24, 8, "Raise an error and\nhalt the run", "layer2", 6.6)
    arrow(ax, (0, 14), (-8, 2), rad=-0.2, label="no")

    save(fig, "fig12_per_alert_triage_activity.png")


# =======================================================================
# Figure -- Memory-Layer Architecture
# =======================================================================
def fig_13():
    fig, ax = new_fig(16, 11)

    zone_label(ax, 2, 96, "READ PATH  (retrieval, before triage)")
    box(ax, 2, 82, 16, 10, "Incoming Alert", "external", 7.3)
    box(ax, 20, 82, 18, 10, "CaseRenderer\n.to_query_text()", "layer3", 6.8)
    box(ax, 40, 82, 18, 10, "EmbeddingFunction\n.encode()", "layer3", 6.8)
    box(ax, 60, 82, 22, 10, "MemoryStore (ChromaDB)\ncollection.query(top-k)", "layer3", 6.6)
    box(ax, 60, 66, 22, 10, "Retriever\nthreshold + diversity filter", "layer3", 6.6)
    for a, b in [(18, 20), (38, 40), (58, 60)]:
        arrow(ax, (a, 87), (b, 87))
    arrow(ax, (78, 82), (78, 76))
    arrow(ax, (60, 71), (40, 58), rad=0.2, label="injected into the LLM prompt")

    zone_label(ax, 2, 60, "WRITE PATH  (after triage)")
    box(ax, 2, 46, 18, 10, "TriagedCase\n(alert + verdict +\nrationale)", "external", 6.8)
    box(ax, 22, 46, 16, 10, "WritePolicy\n.should_write()", "layer3", 6.8)
    box(ax, 40, 46, 18, 10, "CaseRenderer\n.to_document()", "layer3", 6.8)
    box(ax, 60, 46, 22, 10, "EmbeddingFunction.encode()\n-> MemoryStore.add()", "layer3", 6.6)
    for a, b in [(20, 22), (38, 40), (58, 60)]:
        arrow(ax, (a, 51), (b, 51))

    zone_label(ax, 2, 38, "CASE SELECTION  (precedes rendering, on both paths)")
    box(ax, 2, 22, 26, 12, "Case Ranker\n(memory/case_ranker/)\n\nRanks alerts by risk score,\nselects and compacts the\nhighest-severity cases", "layer3", 6.6)
    box(ax, 32, 22, 26, 12, "Compact case digest\n(embedding_input_text)\n\nThe text CaseRenderer and\nEmbeddingFunction consume", "layer3", 6.6)
    arrow(ax, (28, 28), (32, 28))
    arrow(ax, (45, 34), (30, 46), rad=-0.2, label="feeds CaseRenderer above")

    ax.text(2, 12, "Case selection determines which alerts become memory cases before rendering and\n"
                    "embedding occur; retrieval and write-back otherwise follow the paths shown above.",
            fontsize=7.6, color=BLACK)
    save(fig, "fig13_memory_layer_architecture.png")


# =======================================================================
# Figure -- Component Interaction / Integration Diagram
# =======================================================================
def fig_14():
    fig, ax = new_fig(17, 11)

    box(ax, 35, 90, 30, 8, "LLM API  (chat completions endpoint)", "external", 7.5, dashed=True)
    arrow(ax, (44, 90), (30, 80))
    arrow(ax, (56, 90), (70, 80))

    zone_label(ax, 2, 84, "Detection")
    zone_label(ax, 24, 84, "Aggregate Reporting")
    zone_label(ax, 60, 84, "Per-Alert Triage")

    box(ax, 2, 68, 20, 10, "live_capture.py\n(one-shot / --loop)", "layer4a", 7.0)
    arrow(ax, (12, 68), (12, 60), label="POST\n/api/logs")
    box(ax, 2, 48, 20, 10, "Detection API :8000\nfinal_ml_model_v1", "layer2", 6.8)
    arrow(ax, (12, 48), (12, 40))
    box(ax, 2, 28, 20, 10, "Docker Compose\nwraps this service", "external", 6.8)

    box(ax, 30, 55, 24, 9, "live_results.jsonl\n(shared hand-off file)", "layer4a", 6.8)
    arrow(ax, (12, 48), (30, 59), rad=0.1)

    box(ax, 24, 70, 20, 10, "generate_report.py", "layer4a", 7.0)
    arrow(ax, (34, 70), (38, 64), rad=-0.1)
    box(ax, 24, 34, 20, 10, "Report API :8001\nreport_server.py", "layer4a", 6.8)
    arrow(ax, (34, 55), (34, 44))
    box(ax, 24, 14, 20, 10, "React Dashboard", "layer4a", 6.8)
    arrow(ax, (34, 34), (34, 24), label="GET /api/reports")
    ax.text(24, 46, "reports/*.json,*.md", fontsize=6.8, color=BLACK,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#999999", alpha=0.95))

    box(ax, 60, 70, 20, 10, "triage_runner.py", "layer4b", 7.0)
    arrow(ax, (60, 74), (54, 60), rad=0.15)
    box(ax, 60, 34, 20, 10, "triage_verdicts.jsonl", "layer4b", 6.8)
    arrow(ax, (70, 70), (70, 44))
    box(ax, 60, 14, 20, 10, "score_verdicts.py", "layer4b", 6.8)
    arrow(ax, (70, 34), (70, 24))
    box(ax, 84, 14, 14, 10, "ground_truth.csv", "external", 6.6, dashed=True)
    arrow(ax, (84, 19), (80, 19), label="join on uid")

    box(ax, 60, 55, 20, 9, "Case Ranker\n(memory/case_ranker/)", "layer3", 6.6)
    arrow(ax, (60, 59), (54, 59), rad=-0.1)

    ax.text(2, 5, "Connections not labelled with an HTTP verb are file reads/writes on the local filesystem.\n"
                   "Ports 8000/8001 are separate processes; the dashboard is the only browser-facing surface.",
            fontsize=8, color=BLACK)
    save(fig, "fig14_component_interaction.png")


if __name__ == "__main__":
    fig_01()
    fig_02()
    fig_04()
    fig_05()
    fig_06()
    fig_11()
    fig_12()
    fig_13()
    fig_14()
    print("\nAll diagrams generated.")
