from pydantic import BaseModel, Field
from typing import Optional


class InsuranceQuote(BaseModel):
    carrier_name: str = Field(description="Insurance carrier name (e.g., 'Erie Insurance', 'State Farm')")
    policy_type: str = Field(description="Policy type code: HO3, HO5, Auto, BOP, etc.")
    effective_date: Optional[str] = Field(None, description="Policy effective date in ISO format YYYY-MM-DD")
    expiration_date: Optional[str] = Field(None, description="Policy expiration date in ISO format YYYY-MM-DD")
    annual_premium: float = Field(description="Total annual premium in USD")
    monthly_premium: Optional[float] = Field(None, description="Monthly premium if quoted separately")
    deductible: float = Field(description="Primary deductible in USD")
    wind_hail_deductible: Optional[float] = Field(None, description="Separate wind/hail deductible if applicable")
    coverage_limits: dict[str, float] = Field(
        description="Coverage type to limit amount mapping",
        examples=[{
            "dwelling": 300000,
            "other_structures": 30000,
            "personal_property": 150000,
            "loss_of_use": 60000,
            "personal_liability": 100000,
            "medical_payments": 5000
        }]
    )
    endorsements: list[str] = Field(default_factory=list, description="List of endorsements/riders included")
    exclusions: list[str] = Field(default_factory=list, description="List of notable exclusions")
    discounts_applied: list[str] = Field(default_factory=list, description="Discounts applied to this quote")
    confidence: str = Field(description="Extraction confidence: 'high', 'medium', or 'low'")
    notes: Optional[str] = Field(None, description="Any caveats, ambiguities, or extraction notes")
    raw_source: Optional[str] = Field(None, description="Which extraction path was used: 'text' or 'multimodal'")


class QuoteExtractionResult(BaseModel):
    filename: str
    success: bool
    quote: Optional[InsuranceQuote] = None
    error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
