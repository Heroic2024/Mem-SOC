# MemSOC — Deployment Progress README

## 1. Project Overview

MemSOC is an AI-assisted SOC inference pipeline that takes network-flow data, performs binary and multiclass attack detection, generates SHAP-based explanations, creates alerts, and exposes the inference capability through a FastAPI server.

The current deployment architecture is designed around the NF-UNSW-NB15 dataset for deterministic replay and local/API-based demonstration.

---

## 2. Final Deployment Architecture

```text
                    NF-UNSW-NB15
                    Raw Dataset
                         |
                         v
                  Log Generator
               Deterministic Replay
                         |
                        JSON
                         |
                         v
                 FASTAPI SERVER
                  POST /api/logs
                         |
                         v
                 Input Validation
                         |
                         v
                   Preprocessing
                         |
                         v
                Feature Engineering
                    48 features
                         |
                         v
                 Binary LightGBM
                  Benign / Attack
                         |
                    +----+----+
                    |         |
                 BENIGN     ATTACK
                              |
                              v
                     Multiclass LightGBM
                      Attack Category
                              |
                              v
                             SHAP
                        Explanation
                              |
                              v
                       Alert Generator
                              |
                    +---------+---------+
                    |                   |
                    v                   v
              JSON Response        Logging System
                                  application.log
                                  inference.log
                                  alerts.log
```

---

# 3. Work Completed

## 3.1 Binary LightGBM Model — COMPLETED

Saved model:

```text
models/binary_lightgbm.pkl
```

The model expects **48 features** and predicts:

```text
0 -> Benign
1 -> Attack
```

The saved model's feature names and order were verified.

---

## 3.2 Multiclass LightGBM Model — COMPLETED

Saved model:

```text
models/multiclass_lightgbm.pkl
```

The model expects **48 features**.

Learned classes:

```text
Analysis
Backdoor
DoS
Exploits
Fuzzers
Generic
Reconnaissance
Shellcode
Worms
```

The saved model's feature names and order were verified.

---

# 4. External Model Validation — COMPLETED

The models were evaluated against external datasets before moving toward deployment.

## 4.1 NF-ToN-IoT Binary Validation

A 100,000-row random sample was tested.

Results:

```text
Accuracy  : 0.8475
Precision : 0.8802
Recall    : 0.7035
F1 Score  : 0.7820
```

Confusion matrix:

```text
[[57398  3722]
 [11527 27353]]
```

This result was considered sufficiently useful to proceed toward deployment.

---

## 4.2 NF-ToN-IoT Multiclass Validation

The following categories were sampled:

```text
Backdoor
ddos
dos
injection
mitm
password
ransomware
scanning
xss
```

Each category was sampled with 1,000 records.

The model produced learned categories such as:

```text
DoS
Exploits
Backdoor
Reconnaissance
Generic
Fuzzers
```

The test also showed cross-dataset class-mapping differences. Several NF-ToN-IoT categories were predominantly mapped to `DoS` or `Exploits`.

---

## 4.3 NF-BoT-IoT Binary Validation

A 100,000-row random sample was tested.

Results:

```text
Accuracy  : 0.1202
Precision : 0.9969
Recall    : 0.1180
F1 Score  : 0.2110
```

The dataset was extremely imbalanced:

```text
Benign :     51,989
Attack: 16,881,819
```

The poor cross-dataset result was not hidden or artificially improved solely to obtain a better metric.

---

# 5. Inference Pipeline — COMPLETED

Location:

```text
src/inference/inference_pipeline.py
```

The pipeline performs:

```text
Incoming JSON
      |
      v
Input validation
      |
      v
DataFrame creation
      |
      v
48-feature preparation
      |
      v
Binary LightGBM
      |
      +---- Benign -> final result
      |
      +---- Attack
              |
              v
       Multiclass LightGBM
              |
              v
             SHAP
              |
              v
       Alert generation
              |
              v
          JSON result
```

The pipeline was successfully imported and executed.

---

# 6. Inference Pipeline Testing — COMPLETED

## 6.1 Benign Test

A benign flow was processed successfully.

Result:

```text
status: benign
binary prediction: Benign
binary confidence: 1.0000
```

---

## 6.2 Attack Test

A real NF-UNSW-NB15 sample was tested.

Ground truth:

```text
Label  : 1
Attack : Fuzzers
```

Prediction:

```text
Binary prediction     : Attack
Binary confidence     : 1.0000

Multiclass prediction : Fuzzers
Multiclass confidence : 0.7230
```

SHAP explanation was successfully generated.

Top contributing features included:

```text
L4_DST_PORT
LONGEST_FLOW_PKT
TCP_WIN_MAX_OUT
MIN_TTL
IN_BYTES
DNS_QUERY_TYPE
RETRANSMITTED_OUT_BYTES
RETRANSMITTED_IN_BYTES
OUT_BYTES
SRC_TO_DST_IAT_STDDEV
```

Therefore, the complete inference path from a network-flow sample through prediction and explanation was verified.

---

# 7. SHAP Explainability — COMPLETED

Location:

```text
src/explain/shap_explainer.py
```

The implementation uses:

```text
shap.TreeExplainer
```

Each explanation contains:

```text
feature
shap_value
impact
```

Impact is represented as:

```text
positive
negative
```

The explanation is sorted by absolute SHAP value and the top features are returned.

---

# 8. Alert Generator — COMPLETED

Location:

```text
src/alerts/alert_generator.py
```

The alert contains:

```text
Attack type
Confidence
Source port
Destination port
Protocol
Top features
SHAP explanation
```

Example:

```json
{
    "attack": "Fuzzers",
    "confidence": 0.723,
    "src_port": 43944,
    "dst_port": 8088,
    "protocol": 6
}
```

The alert generator is integrated with the inference pipeline.

---

# 9. FastAPI Server — COMPLETED

Location:

```text
src/api/server.py
```

Current endpoints:

```text
GET  /
GET  /health
POST /api/logs
```

Root endpoint tested successfully:

```json
{
    "status": "running",
    "service": "MemSOC API"
}
```

Health endpoint:

```json
{
    "status": "healthy"
}
```

---

# 10. FastAPI -> Inference Integration — COMPLETED

The API was tested using:

```text
test_api.py
```

The test sent a 48-feature network flow to:

```text
POST /api/logs
```

The server returned:

```text
HTTP Status: 200
```

The response successfully contained:

```text
Binary prediction
Multiclass prediction
SHAP explanation
Alert
```

For the tested Fuzzers flow:

```text
Binary       -> Attack
Multiclass   -> Fuzzers
Confidence   -> 0.723
SHAP         -> Generated
Alert        -> Generated
```

This verified the complete API-to-inference integration.

---

# 11. Logging System — COMPLETED

The logging system contains:

```text
logs/
├── application.log
├── inference.log
└── alerts.log
```

### application.log

Used for application/API-level events such as:

```text
API initialization
API processing
Request/application events
```

### inference.log

Used for model-related events such as:

```text
Binary prediction
Multiclass prediction
Confidence
SHAP generation
Inference completion
```

### alerts.log

Used for security alert events such as:

```text
Attack type
Confidence
Network information
Top features
Alert generation
```

The logging system was imported and verified successfully.

Duplicate logging caused by logger propagation was also addressed.

---

# 12. Current API Development Server

During development, the server is run with:

```powershell
python -m uvicorn src.api.server:app --reload
```

The server successfully runs at:

```text
http://127.0.0.1:8000
```

The output confirms:

```text
Uvicorn running
Application startup complete
```

The `--reload` option is being used while files are still being modified.

For the final deployment/demo, the server can be run without reload:

```powershell
python -m uvicorn src.api.server:app
```

---

# 13. Relevant Project Structure

```text
MemSOC/
|
+-- data/
|   +-- external/
|   |   +-- NF-BoT-IoT-v3.csv
|   |   +-- NF-CICIDS2018-v3.csv
|   |   +-- NF-ToN-IoT-v3.csv
|   |
|   +-- processed/
|   |
|   +-- raw/
|       +-- NF-UNSW-NB15-v3.csv
|
+-- models/
|   +-- binary_lightgbm.pkl
|   +-- multiclass_lightgbm.pkl
|
+-- logs/
|   +-- application.log
|   +-- inference.log
|   +-- alerts.log
|
+-- src/
|   +-- alerts/
|   |   +-- alert_generator.py
|   |
|   +-- api/
|   |   +-- __init__.py
|   |   +-- server.py
|   |
|   +-- explain/
|   |   +-- shap_explainer.py
|   |
|   +-- inference/
|   |   +-- __init__.py
|   |   +-- inference_pipeline.py
|   |
|   +-- features/
|   |   +-- feature_engineering.py
|   |
|   +-- preprocessing/
|   |   +-- preprocessor.py
|   |
|   +-- utils/
|       +-- logger.py
|
+-- test_api.py
+-- main.py
+-- requirements.txt
+-- README.md
+-- MemSOC_Demo_README.md
```

---

# 14. What Is NOT Completed Yet

## 14.1 Deterministic Replay Generator — NEXT

Planned location:

```text
src/log_generator/
├── __init__.py
└── replay.py
```

Purpose:

```text
NF-UNSW-NB15 raw dataset
        |
        v
Select network-flow records
        |
        v
Convert records to JSON
        |
        v
Replay deterministically
```

This will replace the current manually selected test flow with realistic replay from the NF-UNSW dataset.

---

## 14.2 Replay -> API Integration — PENDING

After the replay generator works independently:

```text
NF-UNSW
   |
   v
Replay Generator
   |
   v
JSON flow
   |
   v
POST /api/logs
   |
   v
FastAPI
   |
   v
Inference
```

will be implemented.

---

## 14.3 Complete End-to-End Demo — PENDING

The final demonstration will prove:

```text
NF-UNSW-NB15
      |
      v
Deterministic Replay
      |
      v
JSON Network Flow
      |
      v
POST /api/logs
      |
      v
Input Validation
      |
      v
Preprocessing
      |
      v
48 Features
      |
      v
Binary LightGBM
      |
      v
Attack
      |
      v
Multiclass LightGBM
      |
      v
Attack Category
      |
      v
SHAP
      |
      v
Alert Generator
      |
      +----------------------+
      |                      |
      v                      v
JSON Response           Log Files
                         application.log
                         inference.log
                         alerts.log
```

---

# 15. Deployment Completion Status

| Component | Status |
|---|---|
| Binary LightGBM model | Completed |
| Multiclass LightGBM model | Completed |
| External validation | Completed |
| Inference pipeline | Completed |
| Input validation | Completed |
| Feature handling | Completed |
| SHAP explainability | Completed |
| Alert generation | Completed |
| FastAPI server | Completed |
| API -> inference integration | Completed |
| Structured logging | Completed |
| Deterministic replay generator | Next |
| Replay -> API integration | Pending |
| Complete end-to-end demo | Pending |
| Final Linux/server deployment | Pending |

---

# 16. Current Position

The core ML and API deployment path is operational.

The remaining work is mainly the data replay and final end-to-end demonstration layer.

The immediate next task is:

```text
Create deterministic NF-UNSW-NB15 replay generator
```

Then:

```text
Replay
  -> FastAPI
  -> Inference
  -> SHAP
  -> Alert
  -> Logs
```

will complete the planned deployment demonstration.

---

# 17. Design Decision: No Frontend Yet

A frontend is not required at this stage.

The deployment currently focuses on:

```text
Dataset
   |
   v
Log Generator
   |
   v
FastAPI
   |
   v
ML Inference
   |
   v
SHAP
   |
   v
Alerts
   |
   v
Logs
```

This keeps the deployment focused on the SOC inference backend and allows the complete pipeline to be demonstrated through API requests, terminal output, JSON responses, and generated logs.

---

## Immediate Next Step

Build:

```text
src/log_generator/
├── __init__.py
└── replay.py
```

using the NF-UNSW-NB15 raw dataset for deterministic network-flow replay.
