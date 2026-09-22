# MemSOC — ML Progress & Deployment Plan

## 1. Scope

This component covers the ML-based network attack detection system:

- Dataset validation and EDA
- Preprocessing
- Feature engineering
- Binary attack detection
- Multiclass attack classification
- SHAP explainability
- Alert generation
- Local inference
- Planned REST API deployment

The separate LLM and memory-layer work is outside this component.

## 2. Completed Work

### Dataset Validation
Dataset:

`data/raw/NF-UNSW-NB15-v3.csv`

Final dataset:

- 2,365,424 rows
- 55 columns
- 63,425 missing values in `SRC_TO_DST_SECOND_BYTES`
- 14,815 duplicate rows
- 0 constant columns

### Preprocessing
Current preprocessing:

```python
self.df = self.df.drop_duplicates()

self.df["SRC_TO_DST_SECOND_BYTES"] = (
    self.df["SRC_TO_DST_SECOND_BYTES"].fillna(0)
)
```

Dataset-level duplicate removal and missing-value handling are complete.

### Feature Engineering

The current training feature engineering removes:

```text
Attack
Label
IPV4_SRC_ADDR
IPV4_DST_ADDR
FLOW_START_MILLISECONDS
FLOW_END_MILLISECONDS
DNS_QUERY_ID
```

This produces the final **48 model features**.

Targets:

```text
y_binary = Label
y_multi  = Attack
```

Therefore:

```text
55 original columns
        ↓
remove 7 columns
        ↓
48 model features
```

For inference, `Attack` and `Label` will not be present because they are prediction targets.

## 3. Data Splitting

Binary classification:

```text
X Train : 1,880,487
X Test  :   470,122
```

Multiclass attack classification:

```text
Attack X Train : 102,143
Attack X Test  : 25,536
```

## 4. Final Binary LightGBM

The binary model determines:

```text
Benign
or
Attack
```

Final evaluation:

```text
Accuracy  : 1.0000
Precision : 0.9997
Recall    : 0.9999
F1        : 0.9998
```

Saved model:

```text
models/binary_lightgbm.pkl
```

The binary model configuration is finalized.

## 5. Final Multiclass LightGBM

The multiclass model identifies:

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

Final configuration:

```text
n_estimators      = 600
learning_rate     = 0.03
num_leaves        = 63
min_child_samples = 50
random_state      = 42
```

Final class weights:

```text
Analysis          4.0
Backdoor          2.0
DoS               1.8
Exploits          0.5
Fuzzers           0.6
Generic           0.8
Reconnaissance    0.9
Shellcode         3.0
Worms             5.0
```

Final performance:

```text
Accuracy    : 75.62%
Weighted F1 : 75.47%
Macro F1    : 63.02%
```

A separate 100-sample practical test produced:

```text
72 correct
28 incorrect
72% accuracy
```

The **75.62% full test-set accuracy** is the primary evaluation metric. The 72/100 test is treated as a practical sanity check.

Saved model:

```text
models/multiclass_lightgbm.pkl
```

### Class-wise F1

```text
Generic          89.82%
Fuzzers          78.73%
Exploits         76.89%
Reconnaissance   73.49%
Shellcode        68.11%
Worms            58.06%
DoS              45.85%
Analysis         41.87%
Backdoor         33.40%
```

The multiclass model is finalized. No further model tuning is planned.

## 6. SHAP Explainability

SHAP has been integrated to explain the multiclass prediction.

Example:

```json
{
    "feature": "MIN_IP_PKT_LEN",
    "shap_value": 0.7919,
    "impact": "positive"
}
```

Interpretation:

- `positive` — contributed toward the predicted class
- `negative` — pushed away from the predicted class

## 7. Alert Generation

The final alert combines:

- Attack type
- Confidence
- Source port
- Destination port
- Protocol
- Model top features
- SHAP explanation

Example:

```json
{
    "attack": "Exploits",
    "confidence": 0.6308,
    "src_port": 11782,
    "dst_port": 53,
    "protocol": 17,
    "top_features": [
        "L4_SRC_PORT",
        "ICMP_TYPE",
        "SRC_TO_DST_IAT_MAX",
        "L4_DST_PORT",
        "LONGEST_FLOW_PKT"
    ],
    "shap_explanation": [
        {
            "feature": "MIN_IP_PKT_LEN",
            "shap_value": 0.7919,
            "impact": "positive"
        }
    ]
}
```

## 8. Testing Completed

```text
Dataset validation              DONE
EDA                              DONE
Preprocessing                    DONE
Binary evaluation                DONE
Multiclass evaluation            DONE
Class imbalance analysis         DONE
RandomOverSampler experiment     DONE / removed
Class-weight experiments         DONE
Hyperparameter experiments       DONE
Final model selection             DONE
SHAP integration                 DONE
SHAP verification                DONE
100-sample practical test        DONE
Class-wise evaluation             DONE
```

The model configuration is now **frozen**.

## 9. Next Stage — Local Inference Pipeline

The next task is to build:

```text
src/inference/
├── __init__.py
└── inference_pipeline.py
```

The target flow is:

```text
                 JSON Network Log
                         |
                         v
               Input Validation
                         |
                         v
                  Preprocessing
                         |
                         v
                Feature Preparation
                         |
                         v
                 48 Model Features
                         |
                         v
                 Binary LightGBM
                         |
                +--------+--------+
                |                 |
             Benign             Attack
                |                 |
                |                 v
                |        Multiclass LightGBM
                |                 |
                |                 v
                |          Attack Category
                |                 |
                |                 v
                |               SHAP
                |                 |
                +--------+--------+
                         |
                         v
                   Final Alert
```

## 10. Important Inference Requirement

The trained model expects the same model-compatible feature structure used during training.

Therefore:

```text
Training features
        =
Inference features
```

The incoming JSON must be converted into the correct model feature DataFrame before calling `predict()`.

The inference pipeline should reuse the relevant preprocessing logic, but it should **not blindly run dataset-level operations** such as duplicate removal on each individual request.

The inference pipeline also must not require `Attack` or `Label`, because these are the values being predicted.

## 11. Training vs Inference

### Training

```text
Dataset
   ↓
Preprocessing
   ↓
Feature Engineering
   ↓
model.fit()
   ↓
Saved .pkl model
```

### Inference

```text
New JSON
   ↓
Validation
   ↓
Feature preparation
   ↓
model.predict()
   ↓
Prediction
```

Inference will not retrain the models.

## 12. Remaining Testing

After building the local inference pipeline:

### Test 1 — Single valid JSON

```text
JSON
 ↓
Binary
 ↓
Multiclass
 ↓
SHAP
 ↓
Alert
```

### Test 2 — Multiple JSON samples

Verify predictions across different network-flow records.

### Test 3 — Invalid input

Test:

- Missing required feature
- Incorrect data type
- Null value
- Empty JSON
- Unexpected fields

## 13. REST API Deployment — After Inference Testing

Once local inference is verified, wrap it in FastAPI.

Planned endpoints:

```text
POST /api/logs
GET  /api/logs
GET  /api/predictions
```

### Log ingestion

```text
POST /api/logs
```

Receives JSON network logs.

### Application/server logs

```text
GET /api/logs
```

Retrieves application logs.

### Model predictions

```text
GET /api/predictions
```

Retrieves generated detection results.

## 14. Final Deployment Architecture

```text
External Log Source / SIEM
          |
          | POST /api/logs
          v
      FastAPI Server
          |
          v
   Inference Pipeline
          |
          v
    Binary LightGBM
          |
       Attack?
       /     \
     No       Yes
     |         |
  Benign       v
          Multiclass
              |
              v
             SHAP
              |
              v
        Alert Generator
              |
              v
       Prediction Store
          /          \
         v            v
GET /api/logs   GET /api/predictions
```

## 15. Planned Project Structure

```text
MemSOC/
│
├── main.py
│
├── api/
│   ├── __init__.py
│   ├── server.py
│   └── schemas.py
│
├── models/
│   ├── binary_lightgbm.pkl
│   └── multiclass_lightgbm.pkl
│
├── src/
│   ├── preprocessing/
│   ├── features/
│   ├── models/
│   ├── explain/
│   ├── alerts/
│   └── inference/
│
├── logs/
├── data/
└── requirements.txt
```

## 16. Development Roadmap

```text
FINALIZED ML MODELS
        ↓
LOCAL INFERENCE PIPELINE       ← NEXT
        ↓
VALID JSON TESTING
        ↓
INVALID INPUT TESTING
        ↓
FASTAPI
        ↓
POST /api/logs
GET  /api/logs
GET  /api/predictions
        ↓
LOCAL API TESTING
        ↓
SERVER DEPLOYMENT
```

## 17. Important Project Decision

The model configuration is now **frozen**.

No further:

- Random oversampling
- Class-weight experimentation
- Hyperparameter tuning
- Model replacement

will be performed unless a serious implementation problem is discovered.

The remaining work is focused on **using the finalized models correctly in an inference pipeline and deploying them as an API**.
