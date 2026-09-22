"""
Response shapes shared by the two MemSOC APIs.

These describe the contracts that already existed -- they are declared here
so the shape is written down once and shows up in the generated OpenAPI
docs, not to change any payload. The detection endpoint still accepts a
bare JSON object and still returns the InferencePipeline result verbatim;
modelling its full envelope as a strict schema would couple this module to
the frozen detector's output format, which the brief keeps fixed.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Health(BaseModel):
    """Health probe response. Both apps answer on GET /health."""

    status: str


class DetectionHealth(Health):
    pass


class ReportHealth(Health):
    reports_dir: str


class Root(BaseModel):
    """Liveness banner on the detection app's GET /."""

    status: str
    service: str


class BinaryOutcome(BaseModel):
    prediction: str = Field(description="'Attack' or 'Benign'")
    confidence: float


class MulticlassOutcome(BaseModel):
    prediction: str = Field(description="Attack category label")
    confidence: float


class ShapContribution(BaseModel):
    feature: str
    shap_value: float
    impact: str = Field(description="'positive' or 'negative'")


class Verdict(BaseModel):
    """
    What POST /api/logs returns. Documentation of the existing envelope --
    the route returns the pipeline's dict unchanged rather than coercing
    through this model.
    """

    status: str = Field(description="'attack' or 'benign'")
    binary: BinaryOutcome
    multiclass: Optional[MulticlassOutcome] = None
    shap: Optional[List[ShapContribution]] = None
    alert: Optional[Dict[str, Any]] = None


class ReportSummary(BaseModel):
    """One row of GET /api/reports."""

    name: str
    generated_at: str
    flows_in_snapshot: int
    attack_count: int
    attack_rate_pct: float
    overall_risk_level: str
    severity_distribution: Dict[str, int]
    critical_count: int


class ReportList(BaseModel):
    reports: List[ReportSummary]
    retention_limit: int
