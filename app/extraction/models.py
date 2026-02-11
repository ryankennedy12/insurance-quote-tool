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
    coverage_limits: dict[str, float | str] = Field(
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


class CarrierBundle(BaseModel):
    """All quotes from a single carrier for one customer comparison."""
    carrier_name: str = Field(description="Carrier name for column header")
    home: Optional[InsuranceQuote] = Field(None, description="Home/HO3/HO5 quote")
    auto: Optional[InsuranceQuote] = Field(None, description="Auto quote")
    umbrella: Optional[InsuranceQuote] = Field(None, description="Umbrella/excess liability quote")

    @property
    def total_premium(self) -> float:
        """Sum of all policy premiums for this carrier."""
        total = 0.0
        if self.home:
            total += self.home.annual_premium
        if self.auto:
            total += self.auto.annual_premium
        if self.umbrella:
            total += self.umbrella.annual_premium
        return total

    @property
    def policy_types_present(self) -> list[str]:
        """Which policy types have quotes."""
        types = []
        if self.home:
            types.append("home")
        if self.auto:
            types.append("auto")
        if self.umbrella:
            types.append("umbrella")
        return types


class CurrentPolicy(BaseModel):
    """Customer's current coverage for comparison baseline."""
    carrier_name: str = Field(description="Current carrier name")

    # Home
    home_premium: Optional[float] = Field(None, description="Current annual home premium")
    home_dwelling: Optional[float] = Field(None, description="Current dwelling coverage limit")
    home_other_structures: Optional[float] = Field(None, description="Current other structures limit")
    home_liability: Optional[float] = Field(None, description="Current liability limit")
    home_personal_property: Optional[float] = Field(None, description="Current personal property limit")
    home_loss_of_use: Optional[float] = Field(None, description="Current loss of use limit")
    home_deductible: Optional[float] = Field(None, description="Current home deductible")

    # Auto
    auto_premium: Optional[float] = Field(None, description="Current annual auto premium")
    auto_limits: Optional[str] = Field(None, description="Current auto limits e.g. '500/500/250' or '1M CSL'")
    auto_um_uim: Optional[str] = Field(None, description="Current UM/UIM limits")
    auto_comp_deductible: Optional[str] = Field(None, description="Current comprehensive deductible and terms")
    auto_collision_deductible: Optional[float] = Field(None, description="Current collision deductible")

    # Umbrella
    umbrella_premium: Optional[float] = Field(None, description="Current annual umbrella premium")
    umbrella_limits: Optional[str] = Field(None, description="Current umbrella limits e.g. '1M CSL'")
    umbrella_deductible: Optional[float] = Field(None, description="Current umbrella deductible")

    @property
    def total_premium(self) -> float:
        total = 0.0
        if self.home_premium:
            total += self.home_premium
        if self.auto_premium:
            total += self.auto_premium
        if self.umbrella_premium:
            total += self.umbrella_premium
        return total


class ComparisonSession(BaseModel):
    """Complete comparison session with all data."""
    client_name: str
    date: str = Field(description="ISO date YYYY-MM-DD")
    current_policy: Optional[CurrentPolicy] = None
    carriers: list[CarrierBundle] = Field(default_factory=list, description="2-6 carrier bundles")
    sections_included: list[str] = Field(
        default_factory=list,
        description="Which sections are active: 'home', 'auto', 'umbrella'"
    )
