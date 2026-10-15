"""
Content for the MemSOC Technical Design and Architecture Document.

This document describes the system architecture only: what each
component is, what it does, and how components communicate. It does
not report build status, progress, or outstanding work.
"""

SECTIONS = [

    # =====================================================================
    {
        "number": "1",
        "title": "Purpose and Scope",
        "blocks": [
            {"type": "para", "text":
                "This document is the technical design and architecture reference for MemSOC, an "
                "agentic Security Operations Center (SOC) alert-triage system built around a persistent "
                "memory layer. It describes the complete system architecture: data generation, machine "
                "learning-based detection, the two large-language-model triage pipelines that consume the "
                "detector's output, the memory layer that supplies retrieved precedent to triage decisions, "
                "and the deployment architecture that connects these components."},
            {"type": "para", "text":
                "The document is organized so that each architectural component is introduced before it is "
                "explained in detail: an overview establishes the system's four layers and their "
                "relationships, and each subsequent section then describes one layer's internal design, the "
                "modules that implement it, the data it consumes and produces, and the interfaces through "
                "which it communicates with the rest of the system."},
        ],
    },

    # =====================================================================
    {
        "number": "2",
        "title": "System Architecture Overview",
        "blocks": [
            {"type": "para", "text":
                "MemSOC is organized into four architectural layers: a data stream, a machine learning "
                "detector, a memory layer, and a large-language-model triage and reporting layer. The "
                "triage and reporting layer is implemented as two pipelines that share the detector's "
                "output but serve different purposes: an aggregate reporting pipeline that produces a "
                "narrative security report for a dashboard, and a per-alert triage pipeline that produces "
                "one structured, individually scoreable verdict per alert."},
        ],
        "subsections": [
            {"number": "2.1", "title": "Layer Overview", "blocks": [
                {"type": "para", "text":
                    "Figure 2.1 shows the four layers and the direction of data flow between them. Data "
                    "moves from the stream (Layer 1) into the detector (Layer 2), whose output is consumed "
                    "by the triage layer (Layer 4). The triage layer writes triaged cases into the memory "
                    "layer (Layer 3), which in turn supplies retrieved precedent back into the triage "
                    "layer for later alerts. This write-back relationship is what allows the system to "
                    "reason about a new alert in the context of previously triaged, similar alerts."},
                {"type": "figure", "file": "fig01_overall_architecture.png",
                 "caption": "Figure 2.1. The four architectural layers and their data flow, including the "
                            "write-back relationship between the triage layer and the memory layer.",
                 "width_in": 6.3},
            ]},
            {"number": "2.2", "title": "Complete System Architecture", "blocks": [
                {"type": "para", "text":
                    "Figure 2.2 presents the complete architecture in a single diagram: every layer, both "
                    "triage pipelines, the memory layer's components, and the deployment boundary. Data "
                    "generation (top) produces the flow records that the detection layer classifies; its "
                    "output is captured once and then consumed independently by the aggregate reporting "
                    "pipeline, the per-alert triage pipeline, and the memory layer's case-ranking "
                    "component. Each of the following sections examines one of these zones in detail."},
                {"type": "figure", "file": "fig02_complete_architecture.png",
                 "caption": "Figure 2.2. Complete system architecture, showing every layer and both "
                            "triage pipelines in relation to one another.",
                 "width_in": 9.0, "landscape": True},
            ]},
        ],
    },

    # =====================================================================
    {
        "number": "3",
        "title": "Component and Module Architecture",
        "blocks": [
            {"type": "para", "text":
                "Each top-level directory in the system corresponds to one architectural layer. Components "
                "in different directories do not import one another's code; they communicate exclusively "
                "through HTTP requests or through files written to and read from a shared filesystem. This "
                "separation means each layer can be reasoned about, and modified, independently of the "
                "others, provided the file and API contracts between them are preserved."},
            {"type": "figure", "file": "fig04_component_architecture.png",
             "caption": "Figure 3.1. Component and module architecture, grouped by directory and "
                        "architectural layer.",
             "width_in": 9.3, "landscape": True},
            {"type": "table",
             "caption": "Table 3.1. Directory-to-layer mapping.",
             "headers": ["Directory", "Layer", "Role"],
             "col_widths": [1.8, 0.7, 4.0],
             "rows": [
                 ["log_generation/", "1", "Dataset replay, log generation, pipeline orchestration, and a contract test suite"],
                 ["final_ml_model_v1/", "2", "The LightGBM binary and multiclass detector, SHAP explainability, and the FastAPI detection server"],
                 ["LLMTriage/ (aggregate)", "4a", "Statistics computation, LLM narrative generation, and the React dashboard"],
                 ["LLMTriage/ (per-alert)", "4b", "Per-alert LLM triage and its scoring against ground truth"],
                 ["memory/", "3", "Memory-layer architecture, case schema, and the case-ranking component"],
                 ["docs/", "--", "Architecture documentation and design specifications"],
                 ["paths.py, Dockerfile, docker-compose.yml", "--", "Path resolution and containerized deployment of the detection service"],
             ]},
        ],
    },

    # =====================================================================
    {
        "number": "4",
        "title": "End-to-End Data Flow",
        "blocks": [
            {"type": "para", "text":
                "Figure 4.1 traces the system's architecture from the perspective of the data artifacts -- "
                "the files -- that each stage produces and consumes, rather than the components that "
                "produce them. This view makes an important architectural constraint visible directly: "
                "ground_truth.csv, the evaluation oracle, has exactly one path into the system, joining "
                "only into the scoring stage. No component that constructs a prompt for the language model "
                "has access to it."},
            {"type": "figure", "file": "fig05_end_to_end_data_flow.png",
             "caption": "Figure 4.1. End-to-end data flow, traced by file artifact. The path from "
                        "ground_truth.csv is the only one permitted to reach it.",
             "width_in": 9.3, "landscape": True},
            {"type": "table",
             "caption": "Table 4.1. Data artifacts and their roles.",
             "headers": ["File", "Produced by", "Consumed by", "Contents"],
             "col_widths": [1.4, 1.3, 1.6, 2.2],
             "rows": [
                 ["generated_logs.jsonl", "nfv3_log_generator.py", "live_capture.py, triage_runner.py", "48 NetFlow feature values, no label"],
                 ["ground_truth.csv", "nfv3_log_generator.py", "score_verdicts.py", "uid, label, attack -- evaluation oracle"],
                 ["live_results.jsonl", "live_capture.py", "stats_engine.py, triage_runner.py, case_ranker", "Detector output and SHAP attributions; no feature values"],
                 ["reports/*.json, *.md", "generate_report.py", "report_server.py, React dashboard", "Computed statistics and LLM narrative"],
                 ["triage_verdicts.jsonl", "triage_runner.py", "score_verdicts.py", "Per-alert verdict, category, confidence, rationale"],
                 ["memory_input_*.json/.txt", "build_memory_input.py", "the memory layer's embedding step", "Ranked, compacted case digest"],
             ]},
        ],
    },

    # =====================================================================
    {
        "number": "5",
        "title": "Layers 1 and 2: Data Stream and Detection",
        "blocks": [
            {"type": "heading3", "text": "5.1  Data Stream"},
            {"type": "para", "text":
                "The data stream originates from NF-UNSW-NB15-v3, a NetFlow v3-schema dataset of "
                "2.36 million flows. nfv3_log_generator.py first removes the small fraction of rows "
                "containing non-finite feature values, since the detector's own input validation would "
                "reject them; it then applies a seeded selection and shuffle, producing a sample stream "
                "whose order is reproducible across runs while still appearing unordered to the detector. "
                "run_pipeline.py wraps generation, detector startup, and replay into a single command, "
                "reusing the generator module rather than duplicating its logic."},
            {"type": "para", "text":
                "Ground truth is held out structurally rather than by convention: the Label and Attack "
                "columns are written only to the separate ground_truth.csv file and never appear in "
                "generated_logs.jsonl, so no component downstream of log generation can read them unless "
                "it explicitly opens that file. paths.py centralizes path resolution for the whole system, "
                "anchored to its own file location rather than to the current working directory, so the "
                "same command resolves its inputs identically regardless of where it is invoked."},
            {"type": "heading3", "text": "5.2  Detection"},
            {"type": "para", "text":
                "The detector consists of two LightGBM models behind a FastAPI endpoint: a binary "
                "classifier that labels a flow as benign or an attack, and a multiclass classifier that, "
                "for flows labeled an attack, identifies one of nine attack categories. Both models are "
                "frozen: their weights and decision thresholds are fixed and identical for every consumer "
                "of the detection API, which is what allows the two triage pipelines described in Sections "
                "6 and 7 to be compared against a common, unchanging baseline."},
            {"type": "figure", "file": "fig06_detection_pipeline.png",
             "caption": "Figure 5.1. Detection pipeline, from an incoming flow record to the alert "
                        "returned in the API response.",
             "width_in": 3.6},
            {"type": "para", "text":
                "A request first passes validation, which checks that all 48 required features are "
                "present, and numeric coercion, which rejects any value that cannot be parsed as a number. "
                "The binary model then classifies the flow; if it is benign, the pipeline returns "
                "immediately. If it is an attack, the multiclass model assigns a category, SHAP computes "
                "the ten features that most influenced that classification in a deterministic order, and "
                "the alert generator assembles the final response: the attack category, confidence, "
                "source and destination ports, protocol, and the SHAP attributions."},
            {"type": "table",
             "caption": "Table 5.1. Detector specification.",
             "headers": ["Property", "Value"],
             "col_widths": [2.0, 4.5],
             "rows": [
                 ["Binary model", "LightGBM classifier distinguishing benign from attack traffic"],
                 ["Multiclass model", "LightGBM classifier over nine attack categories, class-weighted"],
                 ["Categories", "Exploits, Fuzzers, Reconnaissance, DoS, Generic, Backdoor, Analysis, Shellcode, Worms"],
                 ["Explainability", "SHAP TreeExplainer, top ten features, deterministic ordering"],
                 ["API contract", "POST /api/logs; 48 flat feature fields required, additional fields ignored"],
                 ["Feature count", "48, derived from 55 raw columns after removing two label columns and five identifier or timestamp columns"],
             ]},
        ],
    },

    # =====================================================================
    {
        "number": "6",
        "title": "Layer 4a: Aggregate Reporting Pipeline",
        "blocks": [
            {"type": "para", "text":
                "The aggregate reporting pipeline converts a captured stream of detector outputs into one "
                "comprehensive security report, combining computed statistics with a natural-language "
                "narrative and presenting both through a dashboard. Its purpose is to give an analyst a "
                "single, readable summary of everything the detector has observed over a run, rather than "
                "a verdict on any one alert."},
            {"type": "table",
             "caption": "Table 6.1. Module responsibilities.",
             "headers": ["Module", "Responsibility"],
             "col_widths": [1.7, 4.8],
             "rows": [
                 ["live_capture.py", "Calls the detection API for each flow in the stream and appends its full response to live_results.jsonl"],
                 ["stats_engine.py", "Computes every reported statistic -- attack rate, category breakdown, risk scores, severity distribution -- directly from live_results.jsonl"],
                 ["report_prompt.py", "Constructs the language-model prompt from the computed statistics and validates that the response contains narrative text only"],
                 ["llm_client.py", "Sends the prompt to the language-model API and returns its response"],
                 ["generate_report.py", "Combines the statistics and the narrative into one report document"],
                 ["report_server.py", "Exposes generated reports over an HTTP API for the dashboard to retrieve"],
                 ["dashboard/", "A React application that requests and renders reports; it performs no computation of its own"],
             ]},
            {"type": "para", "text":
                "Statistics and narrative are produced by separate components, joined only at the point "
                "generate_report.py assembles the final document: stats_engine.py never calls the language "
                "model, and report_prompt.py never computes a statistic, so the numbers presented in a "
                "report and the language used to describe them come from independent stages of the "
                "pipeline."},
            {"type": "heading3", "text": "6.1  Component and Data-Flow Diagram"},
            {"type": "figure", "file": "given_flow_diagram.png",
             "caption": "Figure 6.1. Component and data-flow diagram of the aggregate reporting "
                        "pipeline, including its containerized deployment path.",
             "width_in": 9.3, "landscape": True},
            {"type": "para", "text":
                "The NF-UNSW-NB15 dataset feeds a flow generator, whose output reaches the detection API "
                "through one of two paths: live_capture.py, which is the path this pipeline uses, or a "
                "containerized one-shot replay, which is used to confirm the detector accepts the "
                "generated flows and does not feed the reporting pipeline. live_capture.py writes "
                "live_results.jsonl, which the Report API and Dashboard services read and render. The "
                "analyst interacts only with the dashboard; no other component in this diagram is exposed "
                "to them directly."},
            {"type": "heading3", "text": "6.2  Activity Diagram"},
            {"type": "figure", "file": "given_activity_diagram.png",
             "caption": "Figure 6.2. Activity diagram distinguishing the containerized replay path from "
                        "the live-capture path that feeds the reporting pipeline.",
             "width_in": 4.0},
            {"type": "para", "text":
                "The left branch, containerized log generation, is an acceptance path: it confirms that "
                "the detector accepts the generated flows and terminates without writing to "
                "live_results.jsonl. The right branch is the path Section 6 otherwise describes: capture, "
                "statistics, narrative generation, report writing, and dashboard display."},
            {"type": "heading3", "text": "6.3  Sequence Diagram"},
            {"type": "figure", "file": "given_sequence_diagram.png",
             "caption": "Figure 6.3. Sequence diagram of one complete reporting cycle across every "
                        "participant.",
             "width_in": 9.3, "landscape": True},
            {"type": "para", "text":
                "The Flow Generator supplies flows to live_capture.py in a loop; each is posted to the "
                "Detection API and its prediction appended to live_results.jsonl. The Report API reads "
                "that file, computes statistics, requests a narrative from the language model, and writes "
                "the report. The dashboard retrieves and displays it through a single GET request to the "
                "Report API."},
            {"type": "heading3", "text": "6.4  State Diagram"},
            {"type": "figure", "file": "given_state_diagram.png",
             "caption": "Figure 6.4. Lifecycle states of a single network flow as it moves through the "
                        "reporting pipeline.",
             "width_in": 5.4},
            {"type": "para", "text":
                "A flow progresses through the states Generated, Queued, Submitted, Classifying, "
                "Classified, Captured, IncludedInReport, Analysed, Published, and Viewed. "
                "SubmissionFailed is the pipeline's only error state, from which a flow is retried back "
                "into Queued rather than discarded, so every flow either completes the lifecycle or is "
                "explicitly retried."},
        ],
    },

    # =====================================================================
    {
        "number": "7",
        "title": "Layer 4b: Per-Alert Triage Pipeline",
        "blocks": [
            {"type": "para", "text":
                "Where the aggregate pipeline summarizes an entire run, the per-alert triage pipeline "
                "produces one structured verdict for each individual alert, suitable for scoring against "
                "ground truth. This is the pipeline the memory layer is designed to augment: each alert is "
                "triaged independently, in stream order, so that a memory-augmented variant can later "
                "retrieve precedent from earlier verdicts within the same run."},
            {"type": "table",
             "caption": "Table 7.1. Module responsibilities.",
             "headers": ["Module", "Responsibility"],
             "col_widths": [1.7, 4.8],
             "rows": [
                 ["triage_prompt.py", "Constructs the per-alert prompt, presenting the detector's category as a hypothesis rather than a stated fact, and strictly parses the response, rejecting rather than repairing a malformed one"],
                 ["triage_runner.py", "Executes the per-alert loop: load, deduplicate, join feature values, check for an existing verdict, call the language model, validate, and record the result"],
                 ["score_verdicts.py", "Joins recorded verdicts to ground_truth.csv on the alert identifier and computes accuracy metrics"],
             ]},
            {"type": "heading3", "text": "7.1  Pipeline Architecture"},
            {"type": "figure", "file": "fig11_per_alert_triage_pipeline.png",
             "caption": "Figure 7.1. Per-alert triage pipeline, from the existing detection layer through "
                        "to scoring, with the memory layer's retrieval and write-back interfaces.",
             "width_in": 9.3, "landscape": True},
            {"type": "para", "text":
                "A SHAP attribution describes how much a feature contributed to a prediction, but is not "
                "meaningful without the feature's value: knowing that MIN_TTL contributed positively to a "
                "classification is not evidence unless the value of MIN_TTL is also known. Because "
                "live_results.jsonl retains the detector's SHAP attributions but not the underlying flow "
                "feature values, triage_runner.py joins the 48 feature values back in from "
                "generated_logs.jsonl on the alert's uid before constructing the prompt, so that each "
                "attribution can be paired with the value it describes."},
            {"type": "para", "text":
                "The detector's predicted category is deliberately presented to the language model as a "
                "hypothesis to evaluate rather than a fact to confirm. This is an architectural choice: if "
                "the prompt stated the category as given, the language model's task would collapse into "
                "restating the detector's own output, and its verdict would carry no independent "
                "information about whether that classification is correct."},
            {"type": "heading3", "text": "7.2  Resume and Validation Logic"},
            {"type": "figure", "file": "fig12_per_alert_triage_activity.png",
             "caption": "Figure 7.2. Resume and response-validation logic within the per-alert triage "
                        "loop.",
             "width_in": 6.3},
            {"type": "para", "text":
                "Before an alert is sent to the language model, the pipeline checks whether that alert's "
                "identifier already has a recorded verdict, and skips it if so. Because this check happens "
                "before any API call, an interrupted run can always be resumed from where it stopped "
                "without recomputing or re-requesting anything already completed. A response that is not "
                "valid JSON, or that uses a value outside the pipeline's closed vocabulary for a field, is "
                "never repaired or approximated: the run halts with an explicit error, so that a malformed "
                "response can be inspected rather than silently recorded as a verdict."},
            {"type": "heading3", "text": "7.3  Verdict Schema"},
            {"type": "para", "text":
                "Each recorded verdict follows a fixed schema, shown in Table 7.2. The schema reserves "
                "fields for precedent -- precedent_used and precedent_count -- so that a memory-augmented "
                "variant of this pipeline can record which stored cases, if any, informed a given verdict, "
                "without requiring any change to the fields already recorded."},
            {"type": "table",
             "caption": "Table 7.2. triage_verdicts.jsonl field schema.",
             "headers": ["Field", "Type", "Description"],
             "col_widths": [1.6, 0.8, 4.1],
             "rows": [
                 ["verdict", "string", "One of true_positive, false_positive, or inconclusive"],
                 ["attack_category", "string", "One of the detector's observed categories, or none or unknown"],
                 ["confidence", "number", "A value between 0.0 and 1.0, reported by the language model"],
                 ["rationale_summary", "string", "A textual justification, limited to 500 characters"],
                 ["precedent_used", "string", "Identifiers of stored cases that informed this verdict"],
                 ["precedent_count", "integer", "The number of stored cases referenced in precedent_used"],
             ]},
            {"type": "heading3", "text": "7.4  Scoring Architecture"},
            {"type": "para", "text":
                "score_verdicts.py joins triage_verdicts.jsonl to ground_truth.csv on the alert identifier "
                "and computes, from that joined data only: category accuracy, comparing the recorded "
                "attack_category to the ground-truth attack label; precision, recall, and F1, comparing "
                "the recorded verdict to the ground-truth label; and an agreement rate between the "
                "language model's category and the detector's own multiclass prediction, which "
                "distinguishes a language model reasoning independently from one simply restating the "
                "detector's output. This scoring step is the only part of the system permitted to read "
                "ground_truth.csv, and it runs after triage is complete, so a verdict already recorded is "
                "never influenced by the score computed from it."},
        ],
    },

    # =====================================================================
    {
        "number": "8",
        "title": "Layer 3: Memory Layer Architecture",
        "blocks": [
            {"type": "para", "text":
                "The memory layer supplies retrieved precedent to the triage pipeline and records each "
                "triaged case for future retrieval. It is the architectural mechanism by which the system "
                "can reason about a new alert in light of similar alerts triaged earlier in the same run."},
            {"type": "figure", "file": "fig13_memory_layer_architecture.png",
             "caption": "Figure 8.1. Memory-layer architecture: case selection, the read path that "
                        "retrieves precedent, and the write path that records a triaged case.",
             "width_in": 9.3, "landscape": True},
            {"type": "table",
             "caption": "Table 8.1. Memory-layer components.",
             "headers": ["Component", "Role"],
             "col_widths": [1.7, 4.8],
             "rows": [
                 ["Case Ranker", "Scores every alert by a fixed risk formula and selects the highest-severity cases to render, compacted within a bounded token budget"],
                 ["CaseRenderer", "Converts an alert or a triaged case into the text representation used for embedding, applying the same template on both the read and write paths"],
                 ["EmbeddingFunction", "Converts rendered text into a vector, using one fixed model shared by both the read and write paths"],
                 ["MemoryStore", "A persistent vector collection that holds embedded cases and supports similarity search"],
                 ["Retriever", "Executes a similarity query, applies a minimum-similarity threshold, and enforces diversity among the returned cases"],
                 ["WritePolicy", "Determines whether a given triaged case is written to the store"],
             ]},
            {"type": "para", "text":
                "On the read path, an incoming alert is rendered to text by CaseRenderer, encoded to a "
                "vector by EmbeddingFunction, and used to query the store for its most similar prior "
                "cases; the Retriever filters these by similarity and diversity before they are injected "
                "into the language model's prompt as precedent. On the write path, a triaged case -- the "
                "alert together with its verdict and rationale -- is first checked against WritePolicy, "
                "then rendered and embedded by the same CaseRenderer and EmbeddingFunction used on the "
                "read path, and added to the store. Using the same rendering template and the same "
                "embedding model on both paths is what makes a stored case retrievable by a later, "
                "similar alert."},
            {"type": "para", "text":
                "Case selection precedes rendering on both paths. The Case Ranker computes a risk score "
                "for each alert -- the detector's confidence multiplied by a fixed weight assigned to its "
                "attack category -- and ranks alerts accordingly. This ranking determines which cases are "
                "rendered and embedded when the number of triaged alerts exceeds what the memory layer's "
                "token budget can accommodate in a single case digest."},
            {"type": "heading3", "text": "8.1  Case Schema"},
            {"type": "para", "text":
                "A stored case is divided into three parts, each with a distinct role, summarized in "
                "Table 8.2. The embedded text determines what similarity search treats as alike; the "
                "metadata determines what can be filtered or cited in a report; and the sidecar record "
                "preserves the full detail -- the complete feature vector, full rationale, and retrieval "
                "history -- without inflating the size of the vector store itself."},
            {"type": "table",
             "caption": "Table 8.2. Case schema.",
             "headers": ["Part", "Store location", "Contents"],
             "col_widths": [1.4, 1.2, 3.9],
             "rows": [
                 ["Embedding text", "Vector store document", "An alert-only rendering, identical in structure whether the alert is being queried or being stored, so that retrieval measures similarity between alerts rather than between an alert and a stored verdict"],
                 ["Metadata", "Vector store metadata", "Case and run identifiers, the detector's label and score, the recorded verdict and category, and the identifiers of any precedent used"],
                 ["Sidecar record", "A separate file, keyed by case identifier", "The complete feature vector, full rationale text, and every retrieval candidate considered, with its similarity score"],
             ]},
            {"type": "heading3", "text": "8.2  Design Parameters"},
            {"type": "para", "text":
                "The case schema fixes several parameters that determine how retrieval behaves. The "
                "embedded text is alert-only: it excludes the verdict and rationale, so that a query "
                "alert and a stored case are rendered by exactly the same template and occupy the same "
                "region of the embedding space. The attack_category recorded in metadata is the language "
                "model's own categorization of the alert, distinct from the detector's label, which is "
                "recorded separately. Ground-truth labels are never written into the store: memory holds "
                "only what the language model itself concluded about a case, so that the system's stored "
                "precedent reflects its own reasoning rather than the evaluation oracle."},
        ],
    },

    # =====================================================================
    {
        "number": "9",
        "title": "Component Interaction and Deployment Architecture",
        "blocks": [
            {"type": "para", "text":
                "Figure 9.1 presents the system as a network of processes: which components are running "
                "services with a fixed port, which are scripts invoked directly, and which connections are "
                "network calls rather than reads or writes of a shared file."},
            {"type": "figure", "file": "fig14_component_interaction.png",
             "caption": "Figure 9.1. Component interaction diagram: services, ports, and file-based "
                        "hand-offs between components.",
             "width_in": 9.3, "landscape": True},
            {"type": "table",
             "caption": "Table 9.1. Interfaces between components.",
             "headers": ["From", "To", "Mechanism", "Payload"],
             "col_widths": [1.6, 1.6, 1.0, 2.3],
             "rows": [
                 ["live_capture.py", "Detection API", "HTTP POST", "One flow record, 48 features plus envelope fields"],
                 ["triage_runner.py", "live_results.jsonl", "File read", "Previously captured detector output"],
                 ["report_prompt.py, triage_prompt.py", "Language model API", "HTTPS POST", "A chat-completion request at a fixed temperature"],
                 ["Dashboard", "Report API", "HTTP GET", "A generated report, by name"],
                 ["score_verdicts.py", "ground_truth.csv", "File read", "Alert identifier, label, and attack category"],
             ]},
            {"type": "table",
             "caption": "Table 9.2. Containerized services (docker-compose.yml).",
             "headers": ["Service", "Purpose"],
             "col_widths": [1.3, 5.2],
             "rows": [
                 ["pipeline", "Runs the full demonstration sequence: start the detection API, classify a sample, generate a report, and stop"],
                 ["stream", "Emulates a continuous sensor against a resumable cursor"],
                 ["generate", "Rebuilds generated_logs.jsonl from the mounted dataset"],
                 ["paths", "Prints the resolved path layout for diagnostic purposes"],
                 ["tests", "Runs the contract test suite"],
                 ["api", "Publishes the detection API on the host"],
             ]},
            {"type": "para", "text":
                "The detection service is the only component wired into the containerized deployment; the "
                "reporting pipelines, the dashboard, and the memory layer's case-ranking component "
                "communicate with it over the host network. Path resolution is identical in both "
                "environments because every component resolves its inputs through paths.py rather than "
                "through a hard-coded location, which is what allows the container and the host to produce "
                "identical results from the same seed."},
        ],
    },

    # =====================================================================
    {
        "number": "10",
        "title": "Technology Stack and Design Rationale",
        "blocks": [
            {"type": "table",
             "caption": "Table 10.1. Technology choices and their rationale.",
             "headers": ["Technology", "Used for", "Rationale"],
             "col_widths": [1.4, 1.5, 3.6],
             "rows": [
                 ["LightGBM", "Detection", "Efficient on tabular NetFlow features and directly interpretable through SHAP, without the added complexity a deep network would introduce for this data"],
                 ["SHAP (TreeExplainer)", "Per-alert explainability", "Produces exact, deterministically ordered attributions for tree-based models"],
                 ["FastAPI and uvicorn", "Detection API, Report API", "Asynchronous request handling with automatic input validation"],
                 ["React and Vite", "Dashboard presentation", "Component reuse across report sections and a fast development cycle"],
                 ["ChromaDB", "Vector store for the memory layer", "On-disk persistence with per-entry metadata filtering, avoiding a hosted vector-database dependency"],
                 ["sentence-transformers", "Embedding model for the memory layer", "Runs locally, avoiding per-call cost and the non-determinism of a remote embedding API"],
             ]},
        ],
    },

    # =====================================================================
    {
        "number": "11",
        "title": "Governing Design Decisions",
        "blocks": [
            {"type": "para", "text":
                "The decisions in Table 11.1 constrain how components in this architecture may be built or "
                "modified. They exist to preserve a controlled comparison between a memoryless triage "
                "pipeline and a memory-augmented one, and to prevent the evaluation oracle from reaching "
                "any component that constructs a prompt."},
            {"type": "table",
             "caption": "Table 11.1. Governing design decisions.",
             "headers": ["Decision", "Rationale"],
             "col_widths": [1.9, 4.6],
             "rows": [
                 ["Detector weights and thresholds are fixed", "Both triage pipelines must be compared against an identical, unchanging detection layer"],
                 ["Ground truth is never passed into a prompt", "Enforced structurally: generated_logs.jsonl, the file every prompt-constructing component reads from, carries no label at all"],
                 ["Alerts are triaged individually, never batched", "Batching would let later alerts in a batch bypass the memory layer's write-back ordering"],
                 ["An existing verdict is checked before any API call", "Makes an interrupted run resumable at no cost beyond the check itself"],
                 ["A malformed language-model response halts the run rather than being repaired", "Prevents an unrecorded, silent correction from entering the stored record"],
                 ["The detector's category is presented as a hypothesis, not a given", "Prevents the language model's task from collapsing into restating the detector's own output"],
                 ["The memory layer's token-budget check uses a heuristic estimator rather than a full tokenizer", "Avoids a large additional dependency for a bound that only needs to be conservative, not exact"],
                 ["Captured records are deduplicated by alert identifier before ranking", "A flow replayed more than once must not occupy more than one ranked position"],
                 ["The vector store is a single collection, never partitioned by attack category", "Partitioning by label would build a label-based prior into retrieval, undermining similarity search based on alert content alone"],
             ]},
        ],
    },

    # =====================================================================
    {
        "number": "Appendix",
        "title": "File and Module Index",
        "blocks": [
            {"type": "table",
             "caption": "Table A.1. Complete file index by directory.",
             "headers": ["Path", "Layer", "Role"],
             "col_widths": [2.9, 0.6, 3.0],
             "rows": [
                 ["log_generation/nfv3_log_generator.py", "1", "Dataset to generated_logs.jsonl and ground_truth.csv"],
                 ["log_generation/replay_to_api.py", "1", "One-shot replay through the detection API"],
                 ["log_generation/stream_to_api.py", "1", "Continuous, resumable sensor emulation"],
                 ["log_generation/run_pipeline.py", "1", "Single-command pipeline orchestration"],
                 ["log_generation/test_pipeline.py", "1", "Contract test suite"],
                 ["final_ml_model_v1/src/api/server.py", "2", "Detection API, POST /api/logs"],
                 ["final_ml_model_v1/src/inference/inference_pipeline.py", "2", "Validation and prediction"],
                 ["final_ml_model_v1/src/explain/shap_explainer.py", "2", "SHAP TreeExplainer wrapper"],
                 ["final_ml_model_v1/src/alerts/alert_generator.py", "2", "Alert assembly"],
                 ["LLMTriage/live_capture.py", "4a", "Captures detector output to live_results.jsonl"],
                 ["LLMTriage/stats_engine.py", "4a", "Statistics and risk scoring"],
                 ["LLMTriage/report_prompt.py", "4a", "Narrative prompt construction and validation"],
                 ["LLMTriage/generate_report.py", "4a", "Report assembly"],
                 ["LLMTriage/report_server.py", "4a", "Report retrieval API"],
                 ["LLMTriage/dashboard/", "4a", "React presentation layer"],
                 ["LLMTriage/triage_prompt.py", "4b", "Per-alert prompt construction and verdict parsing"],
                 ["LLMTriage/triage_runner.py", "4b", "Per-alert triage loop"],
                 ["LLMTriage/score_verdicts.py", "4b", "Scoring against ground truth"],
                 ["memory/case_ranker/build_memory_input.py", "3", "Case ranking and compaction"],
                 ["memory/case_ranker/risk.py", "3", "Risk-scoring formula"],
                 ["memory/case_ranker/token_estimator.py", "3", "Token-budget estimation"],
                 ["paths.py", "--", "Central path resolution"],
                 ["Dockerfile, docker-compose.yml", "--", "Containerized deployment of the detection service"],
             ]},
        ],
    },
]
