# MemSOC: Memory-Augmented AI SOC Analyst

MemSOC is an AI-powered Security Operations Center (SOC) analyst designed to automate network intrusion detection, explain attack decisions, and generate structured security alerts. The project uses machine learning for attack detection and classification, with future integration of explainable AI, memory augmentation, and Large Language Models (LLMs).

---

## Current Project Status

### Completed

- Dataset loading
- Dataset validation
- Exploratory Data Analysis (EDA)
- Data preprocessing
- Feature engineering
- Binary attack detection model
- Multi-class attack classification model
- Alert generation pipeline

### In Progress

- Improving multiclass model performance
- SHAP-based explainability

### Planned

- Offline training pipeline
- Real-time inference pipeline
- Memory layer integration
- LLM-powered SOC analyst

---

## Dataset

Current dataset:

- **NF-UNSW-NB15-v3**

Dataset statistics after preprocessing:

- Total Samples: **2,350,609**
- Features Used: **48**
- Binary Classes:
  - Benign
  - Attack
- Multi-class Attack Categories:
  - Analysis
  - Backdoor
  - DoS
  - Exploits
  - Fuzzers
  - Generic
  - Reconnaissance
  - Shellcode
  - Worms

---

## Project Structure

```
MemSOC/
│
├── configs/
├── data/
│   └── raw/
│
├── models/
│
├── notebooks/
├── outputs/
├── reports/
│
└── src/
    ├── alerts/
    ├── dataset/
    ├── eda/
    ├── explainability/
    ├── features/
    ├── models/
    ├── preprocessing/
    └── utils/
```

---

## Pipeline

```
NF-UNSW-NB15 Dataset
        │
        ▼
Dataset Loader
        │
        ▼
Dataset Validator
        │
        ▼
EDA
        │
        ▼
Preprocessing
        │
        ▼
Feature Engineering
        │
        ▼
Train/Test Split
        │
        ▼
Binary LightGBM
        │
        ▼
Multiclass LightGBM
        │
        ▼
Alert Generator
```

---

## Modules Implemented

### Dataset Loader

- Loads the NF-UNSW-NB15 dataset
- Performs path validation
- Returns a Pandas DataFrame

---

### Dataset Validator

Performs several quality checks including:

- Dataset dimensions
- Memory usage
- Missing values
- Duplicate rows
- Constant columns
- Attack distribution
- Label distribution

---

### Exploratory Data Analysis (EDA)

Current analysis includes:

- Attack distribution visualization
- Class frequency inspection

---

### Preprocessing

Current preprocessing steps:

- Duplicate removal
- Missing value handling

---

### Feature Engineering

Current feature engineering includes:

- Removal of target columns
- Removal of identifier columns
- Selection of training features
- Binary labels
- Multi-class labels

---

### Train/Test Split

Binary model:

- 80% Training
- 20% Testing

Multi-class model:

- Uses only attack samples
- 80% Training
- 20% Testing

---

### Binary Classification Model

Model:

- LightGBM Classifier

Task:

- Detect whether network traffic is:
  - Benign
  - Attack

Current performance:

- Accuracy: ~100%
- Precision: ~99.97%
- Recall: ~99.99%
- F1 Score: ~99.98%

---

### Multi-class Classification Model

Model:

- LightGBM Classifier

Task:

Predict attack categories including:

- Analysis
- Backdoor
- DoS
- Exploits
- Fuzzers
- Generic
- Reconnaissance
- Shellcode
- Worms

Current performance:

- Accuracy: ~70%

Future work focuses on improving this model.

---

### Alert Generator

Generates structured JSON alerts containing:

- Predicted attack
- Confidence score
- Source port
- Destination port
- Protocol
- Top contributing features (currently based on model feature importance)

Example:

```json
{
    "attack": "Generic",
    "confidence": 0.335,
    "src_port": 21697,
    "dst_port": 15726,
    "protocol": 6,
    "top_features": [
        "L4_SRC_PORT",
        "L4_DST_PORT",
        "ICMP_TYPE",
        "LONGEST_FLOW_PKT",
        "IN_BYTES"
    ]
}
```

---

## Technologies Used

- Python
- Pandas
- NumPy
- Scikit-learn
- LightGBM
- Matplotlib
- SHAP (integration in progress)

---

## Current Challenges

The multiclass classifier currently achieves approximately **70% accuracy** due to class imbalance within the dataset.

The next development phase focuses on:

- Class weighting
- Hyperparameter tuning
- Feature selection
- Explainability using SHAP

---

## Future Roadmap

- Improve multiclass model performance
- Implement SHAP explainability
- Separate offline training and inference pipelines
- Integrate vector memory for historical alert retrieval
- Connect the alert pipeline to an LLM for automated SOC analysis

---

## License

This project is developed for research and educational purposes.