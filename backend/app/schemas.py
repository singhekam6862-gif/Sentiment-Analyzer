from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AspectKey(str, Enum):
    """Keyword-lexicon aspects for the rule-based path (TWS earbuds template)."""

    SOUND_QUALITY = "sound_quality"
    ANC_NOISE_CANCELLATION = "anc_noise_cancellation"
    MIC_CALL_QUALITY = "mic_call_quality"
    BATTERY_LIFE = "battery_life"
    COMFORT_BUILD = "comfort_build"
    VALUE_FOR_MONEY = "value_for_money"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Raw Scraped Review Model ---


class RawReview(BaseModel):
    """Raw review extracted by scraper before NLP processing."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    review_id: str
    platform: Literal["flipkart"] = "flipkart"
    product_query: str
    rating: int = Field(ge=1, le=5)
    title: str | None = None
    text: str
    review_date: str
    verified_purchase: bool = False
    helpful_votes: int = Field(ge=0, default=0)
    reviewer_name: str = "Anonymous"

    @model_validator(mode="before")
    @classmethod
    def sync_author_and_reviewer_name(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "author" in data and ("reviewer_name" not in data or not data["reviewer_name"]):
                data["reviewer_name"] = data["author"]
            elif "reviewer_name" in data and "author" not in data:
                data["author"] = data["reviewer_name"]
        return data

    @property
    def author(self) -> str:
        return self.reviewer_name


# --- /api/v3 contract (SPEC.md Section C) ---

Polarity = Literal["praise", "complaint", "mixed"]
Group = Literal["product", "fulfillment", "suspicious"]


class CatalogueProduct(StrictModel):
    id: str
    name: str
    category: str
    review_count: int = Field(ge=0)


class AnalysisRequest(StrictModel):
    product_id: str | None = None
    url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def exactly_one_flipkart_source(self) -> "AnalysisRequest":
        if (self.product_id is None) == (self.url is None):
            raise ValueError("Send exactly one of product_id or url")
        if self.url is not None and not self.url.startswith(("https://www.flipkart.com/", "https://flipkart.com/")):
            raise ValueError("url must be a https://www.flipkart.com/ product link")
        return self


class Product(StrictModel):
    id: str
    name: str
    category: str
    source_url: str | None
    data_source: Literal["live_scrape", "catalogue"]
    collected_on: date | None


class Verdict(StrictModel):
    headline: str
    warning: str | None
    generated_by: Literal["groq", "gemini", "rule_based"]


class Rating(StrictModel):
    average: float = Field(ge=0, le=5)
    count: int = Field(ge=0)
    distribution: list[int] = Field(min_length=5, max_length=5)


class FunnelGroup(StrictModel):
    count: int = Field(ge=0)
    reason: str


class Funnel(StrictModel):
    collected: int = Field(ge=0)
    suspicious: FunnelGroup
    fulfillment: FunnelGroup
    analysed: int = Field(ge=0)


class UseCase(StrictModel):
    name: str
    verdict: Literal["good", "okay", "poor", "too_few"]
    reason: str
    review_count: int = Field(ge=0)


class Quote(StrictModel):
    review_id: str
    text: str
    polarity: Polarity


class Aspect(StrictModel):
    key: str
    label: str
    praise: int = Field(ge=0)
    complaints: int = Field(ge=0)
    mixed: int = Field(ge=0)
    confidence: Literal["high", "medium", "low"]
    quotes: list[Quote] = Field(max_length=4)


class Claim(StrictModel):
    text: str
    review_ids: list[str]


class Review(StrictModel):
    review_id: str
    author: str
    rating: int = Field(ge=1, le=5)
    title: str | None
    text: str
    review_date: date
    verified_purchase: bool
    helpful_votes: int = Field(ge=0)
    group: Group
    sentiment: Literal["positive", "negative", "neutral"]
    aspects: list[str]
    flags: list[str]


class Analysis(StrictModel):
    product: Product
    verdict: Verdict
    rating: Rating
    funnel: Funnel
    use_cases: list[UseCase] = Field(max_length=6)
    aspects: list[Aspect] = Field(max_length=8)
    pros: list[Claim] = Field(max_length=3)
    cons: list[Claim] = Field(max_length=3)
    reviews: list[Review]


class AnalysisJob(StrictModel):
    job_id: str
    status: Literal["queued", "fetching", "analysing", "done", "failed"]
    message: str
    result: Analysis | None = None
    error: str | None = None
