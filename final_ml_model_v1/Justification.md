# Network Intrusion Detection & Attack Classification

## Project Overview

This project implements a two-stage machine learning pipeline for
network intrusion detection and attack classification using LightGBM.
The system first determines whether network traffic is **Benign** or an
**Attack**. If the traffic is identified as an attack, a second
multiclass classifier predicts the specific attack category.

The project focuses on building a practical and interpretable intrusion
detection pipeline rather than optimizing the multiclass model
indefinitely.

## Detection Pipeline

``` text
                    Network Traffic
                          │
                          ▼
                  Binary LightGBM
                          │
             ┌────────────┴────────────┐
             │                         │
          Benign                    Attack
                                       │
                                       ▼
                               Multiclass LightGBM
                                       │
                                       ▼
                              Attack Classification
                                       │
                                       ▼
                                      SHAP
```

## Models

### 1. Binary Classifier

The binary LightGBM model identifies whether the input network traffic
is:

-   **Benign**
-   **Attack**

The binary classifier achieves approximately:

-   **Accuracy:** \~100%
-   **F1 Score:** 99.98%

This indicates that the model is highly effective at distinguishing
attack traffic from benign traffic within the evaluated test set.

### 2. Multiclass Classifier

For traffic identified as an attack, the multiclass LightGBM model
predicts one of nine attack categories.

Evaluation results:

  Metric               Result
  -------------- ------------
  Test samples         25,536
  Accuracy         **75.62%**
  Weighted F1      **75.47%**
  Macro F1         **63.02%**

The difference between weighted F1 and macro F1 is largely explained by
class imbalance. Large classes have a greater influence on weighted
metrics, while macro F1 gives each attack category equal importance.

## Per-Class Performance

  Attack Category       F1 Score
  ----------------- ------------
  Generic             **89.82%**
  Fuzzers             **78.73%**
  Exploits            **76.89%**
  Reconnaissance      **73.49%**
  Shellcode           **68.11%**
  Worms               **58.06%**
  DoS                 **45.85%**
  Analysis            **41.87%**
  Backdoor            **33.40%**

These results show that the multiclass model is learning meaningful
patterns across several attack categories. However, performance varies
considerably between classes, particularly for minority categories.

## Why 75.62% Multiclass Accuracy Is Defensible

The multiclass dataset is highly imbalanced. Some attack categories
contain substantially more samples than others, while categories such as
Analysis and Worms contain relatively few samples.

Therefore, accuracy should not be considered in isolation.

The model achieves strong F1 scores for several important categories,
including:

-   Generic
-   Fuzzers
-   Exploits
-   Reconnaissance

At the same time, lower F1 scores for Backdoor, Analysis, and DoS show
that the model has difficulty distinguishing some attack types.

This means the model is not simply achieving approximately 75% accuracy
by predicting the majority class. It demonstrates meaningful
classification capability across multiple attack categories.

## Evaluation Strategy

The project reports multiple metrics to provide a more reliable
evaluation:

-   **Accuracy** -- overall proportion of correctly classified samples.
-   **Weighted F1** -- accounts for class support and is useful for
    imbalanced datasets.
-   **Macro F1** -- calculates the F1 score for each class equally and
    therefore highlights minority-class performance.
-   **Per-class F1** -- shows which individual attack categories the
    model handles well or poorly.

The combination of these metrics provides a more complete picture than
accuracy alone.

## Model Interpretation with SHAP

SHAP is used to provide model explainability.

The purpose of SHAP is to identify which network traffic features
contributed to a model prediction. This can help explain why traffic was
classified as benign or malicious and, in the multiclass stage, why a
particular attack category was predicted.

This improves the interpretability of the machine learning pipeline and
can be useful for security analysts investigating alerts.

## Important Limitation

The reported **75.62% accuracy is a test-set result**. It should not be
interpreted as a guarantee that 75% of unseen real-world network traffic
will always be classified correctly.

Real-world network traffic can differ from the training and test
distributions because of:

-   New attack techniques
-   Changes in network behavior
-   Different network environments
-   Previously unseen traffic patterns
-   Class distribution changes

Therefore, deployment should include continuous validation and
monitoring.

## Current Project Position

The binary classifier provides very strong attack-vs-benign detection,
while the multiclass classifier is the primary limitation of the current
system.

Rather than continuing to tune the model solely to increase the
multiclass accuracy, the project proceeds to the **inference/API testing
stage**.

The focus at this stage is to verify that the trained models can:

1.  Accept network traffic features as input.
2.  Perform binary classification.
3.  Route attack traffic to the multiclass classifier.
4.  Predict the corresponding attack category.
5.  Generate SHAP-based explanations.
6.  Return the results in a structured JSON response.

## Expected Inference Flow

``` text
Input JSON
    │
    ▼
Feature Validation
    │
    ▼
Binary Model
    │
    ├── Benign ──────► Benign Result
    │
    └── Attack
          │
          ▼
    Multiclass Model
          │
          ▼
    Attack Category
          │
          ▼
    SHAP Explanation
          │
          ▼
    JSON Response
```

## Key Results

  Component                Result
  ------------------------ ---------------------------------
  Binary detection         **\~100% Accuracy / 99.98% F1**
  Multiclass detection     **75.62% Accuracy**
  Multiclass weighted F1   **75.47%**
  Multiclass macro F1      **63.02%**
  Multiclass classes       **9 attack categories**
  Explainability           **SHAP**
  Primary model            **LightGBM**

## Conclusion

The project demonstrates a strong two-stage approach to network
intrusion detection. The binary classifier performs exceptionally well
at distinguishing benign traffic from attacks, while the multiclass
classifier achieves **75.62% accuracy and 63.02% macro F1** across nine
attack categories.

The multiclass results should be interpreted in the context of
significant class imbalance and varying per-class performance. Reporting
accuracy together with macro F1, weighted F1, and per-class F1 provides
a more credible assessment of the system.

The current objective is therefore to proceed with **inference and API
testing**, validating the complete detection and explainability pipeline
rather than further tuning the model.
