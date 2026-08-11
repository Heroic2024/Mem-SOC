# MemSOC --- ML Detection Demo

## 1. Project Overview

MemSOC is a machine-learning-based network attack detection system. The
current implementation focuses on detecting whether network traffic is
benign or malicious, identifying the type of attack, and providing a
SHAP-based explanation for the prediction.

The current ML pipeline does not include an LLM or memory layer. Those
components are outside the scope of this implementation.

## 2. Current Detection Pipeline

``` text
Network Flow / JSON Log
        |
        v
Input Features
        |
        v
Preprocessing
        |
        v
Feature Engineering
        |
        v
Binary LightGBM
        |
   +----+----+
   |         |
Benign     Attack
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
       Explainable Alert
```

The binary model first determines whether the traffic is benign or an
attack. If an attack is detected, the multiclass model identifies the
attack category. SHAP then explains which features contributed most to
the prediction.

## 3. Dataset Processing

The current run used the NF-UNSW-NB15-v3 dataset.

-   Original rows: **2,365,424**
-   Original columns: **55**
-   Memory usage: approximately **1.06 GB**
-   Duplicate rows detected: **14,815**
-   Missing values: **63,425**
-   Missing values were found in `SRC_TO_DST_SECOND_BYTES`
-   Duplicate rows were removed and missing values were handled during
    preprocessing.
-   Rows used for feature engineering: **2,350,609**
-   Features used by the models: **48**

Attack categories include Exploits, Fuzzers, Generic, Reconnaissance,
DoS, Backdoor, Shellcode, Analysis, and Worms.

## 4. Model Performance

### Binary Classification

The binary LightGBM model determines whether traffic is benign or an
attack.

  Metric             Result
  ----------- -------------
  Accuracy      **100.00%**
  Precision      **99.97%**
  Recall         **99.99%**
  F1 Score       **99.98%**

Test set size: **470,122 samples**.

### Multiclass Classification

The multiclass LightGBM model identifies the specific attack category
after traffic has been classified as an attack.

  Metric              Result
  ------------- ------------
  Accuracy        **75.62%**
  Weighted F1        **75%**
  Macro F1           **63%**

Multiclass test set: **25,536 attack samples**.

### Class-wise performance

  Attack Type        Precision   Recall       F1
  ---------------- ----------- -------- --------
  Analysis              31.60%   62.04%   41.87%
  Backdoor              44.25%   26.82%   33.40%
  DoS                   47.13%   44.64%   45.85%
  Exploits              85.34%   69.97%   76.89%
  Fuzzers               69.03%   91.60%   78.73%
  Generic               90.77%   88.88%   89.82%
  Reconnaissance        79.24%   68.52%   73.49%
  Shellcode             63.90%   72.90%   68.11%
  Worms                 60.00%   56.25%   58.06%

## 5. 100-Sample Demonstration Test

A separate test was performed using 100 attack samples from the
multiclass test set.

  Result                         Count
  ----------------------- ------------
  Total samples                    100
  Correct predictions           **72**
  Incorrect predictions         **28**
  Sample accuracy           **72.00%**
  Average confidence        **71.58%**

The demonstration therefore correctly classified **72 out of 100**
attack samples. This small-sample result should not replace the full
held-out test-set evaluation.

## 6. Human-Readable Demo Output

For a project demonstration, the raw JSON can be explained in a cleaner
format:

``` text
============================================================
                 MEMSOC DETECTION ALERT
============================================================

Detection Result : ATTACK
Attack Type      : Fuzzers
Confidence       : 72.28%

Network Details
------------------------------------------------------------
Source Port      : 48171
Destination Port : 445
Protocol         : TCP (6)

------------------------------------------------------------
SHAP EXPLANATION
------------------------------------------------------------

1. L4_DST_PORT
   SHAP Value : +2.364648
   Impact     : Positive

2. MIN_TTL
   SHAP Value : +0.583404
   Impact     : Positive

3. NUM_PKTS_128_TO_256_BYTES
   SHAP Value : +0.552565
   Impact     : Positive

4. DNS_QUERY_TYPE
   SHAP Value : +0.447825
   Impact     : Positive

5. RETRANSMITTED_OUT_BYTES
   SHAP Value : +0.162511
   Impact     : Positive

6. ICMP_TYPE
   SHAP Value : -0.149616
   Impact     : Negative

7. OUT_BYTES
   SHAP Value : +0.133999
   Impact     : Positive

8. LONGEST_FLOW_PKT
   SHAP Value : -0.132470
   Impact     : Negative

9. RETRANSMITTED_IN_BYTES
   SHAP Value : +0.092530
   Impact     : Positive

10. L4_SRC_PORT
    SHAP Value : +0.073241
    Impact     : Positive

============================================================
                     FINAL ALERT
============================================================

ATTACK DETECTED: Fuzzers
Confidence: 72.28%

The alert contains the predicted attack category,
network-flow information, important features, and
SHAP-based explanation.
```

## 7. How to Explain the SHAP Result

A **positive SHAP value** means the feature contributed toward the
model's selected prediction. A **negative SHAP value** means the feature
pushed the model away from the selected prediction. The magnitude
indicates how strongly that feature contributed for the particular
sample.

For example, `L4_DST_PORT` has a SHAP value of `+2.364648`, so it was a
strong positive contributor toward the Fuzzers prediction for this
sample.

## 8. Demo Flow

When running `python main.py`, explain the output in this order:

1.  **Dataset Loading** --- loads the network-flow dataset.
2.  **Dataset Validation** --- checks size, missing values, duplicates,
    constant columns, and label distributions.
3.  **Preprocessing** --- removes duplicate records and handles missing
    values.
4.  **Feature Engineering** --- prepares the 48 model features.
5.  **Binary LightGBM** --- determines Benign vs Attack.
6.  **Multiclass LightGBM** --- identifies the attack category.
7.  **SHAP** --- explains the important features behind the prediction.
8.  **Alert Generation** --- produces the final explainable alert.

## 9. Current Project Status

### Completed

-   Dataset loading and validation
-   Exploratory data analysis
-   Data preprocessing
-   Feature engineering
-   Binary LightGBM model
-   Multiclass LightGBM model
-   Model evaluation
-   Model saving
-   100-sample testing
-   SHAP explainability
-   Explainable alert generation
-   GitHub project setup

### Current Results

``` text
Binary Classification
Accuracy : 100.00%
F1 Score : 99.98%

Multiclass Classification
Full Test Accuracy : 75.62%

100-Sample Demonstration
Accuracy : 72.00%
```

## 10. Planned Deployment Phase

The next stage is to expose the existing ML pipeline as a service. The
planned flow is:

``` text
Network / Application Logs
            |
            v
       Log Input API
            |
            v
    Input Validation
            |
            v
Preprocessing + Feature Engineering
            |
            v
      Binary LightGBM
            |
       +----+----+
       |         |
    Benign     Attack
                 |
                 v
       Multiclass LightGBM
                 |
                 v
               SHAP
                 |
                 v
          Detection Alert API
```

The deployment phase will allow external systems to submit JSON
network-flow logs and receive structured detection results.

## 11. Accuracy Statement for Presentation

The most appropriate statement for the project presentation is:

> **"The multiclass model achieved 75.62% accuracy on the full held-out
> test set of 25,536 attack samples. In a separate 100-sample
> demonstration, it correctly classified 72 samples, giving 72% sample
> accuracy."**

This clearly distinguishes the formal evaluation from the smaller
demonstration test.

## 12. Scope

The current project scope is:

**Network Attack Detection + Attack Classification + Explainability**

The current implementation does **not** include an LLM-based SOC analyst
or memory layer. Those components are outside the scope of this ML
detection module.
