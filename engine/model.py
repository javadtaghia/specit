from pydantic import BaseModel, Field
from typing import Literal


class Evidence(BaseModel):
    source_id: str
    locator: str
    quote: str = ''


class Rule(BaseModel):
    id: str
    statement: str
    classification: Literal['source_defined', 'design_proposed', 'unresolved'] = 'source_defined'
    evidence: list[Evidence] = Field(default_factory=list)


class SystemItem(BaseModel):
    name: str
    responsibility: str = ''
    ownership: str = ''


class GlossaryItem(BaseModel):
    term: str
    definition: str = ''


class Process(BaseModel):
    id: str
    name: str
    description: str = ''
    actors: list[str] = Field(default_factory=list)
    trigger: str = ''
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Literal['high', 'medium', 'low'] = 'medium'


class Catalogue(BaseModel):
    project_name: str
    project_summary: str = ''
    processes: list[Process] = Field(default_factory=list)
    shared_actors: list[str] = Field(default_factory=list)
    systems: list[SystemItem] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    nfrs: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class Artifact(BaseModel):
    process_id: str
    workflow_md: str
    boundaries_md: str
    domain_md: str
    states_md: str
    findings: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    score: int = Field(ge=0, le=100)
    summary: str = ''
    critical: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    model_issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class Foundation(BaseModel):
    constitution_md: str
    specification_md: str
    clarification_md: str


class Planning(BaseModel):
    plan_md: str
    tasks_md: str


class CodeBundle(BaseModel):
    files: dict[str, str] = Field(default_factory=dict)
    notes: str = ''


class ScopedReview(BaseModel):
    verdict: Literal['looks_good', 'needs_minor_edits', 'needs_rework'] = 'needs_minor_edits'
    summary: str = ''
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class SingleDocUpdate(BaseModel):
    markdown: str
    change_summary: str = ''
