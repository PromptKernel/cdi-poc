"""Response models (they become the OpenAPI schema)."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class Health(BaseModel):
    status: str
    auth_required: bool


class Freshness(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: Optional[int] = Field(None, description="Store schema version the baseline was written with")
    commits: dict[str, str] = Field(description="commit id of every logical repo the baseline was built from")
    loaded_at: Optional[str] = None
    mode: Optional[str] = Field(None, description="full | incremental | full-fallback")
    counts: Optional[dict[str, int]] = None


class RepoInfo(BaseModel):
    path: str
    kind: str


class Meta(BaseModel):
    source: str = Field(description="always 'live-api' for this service")
    store: str = Field(description="json | neo4j")
    baseline: Freshness
    counts: dict[str, int]
    repos: dict[str, RepoInfo]
    notice: str


class Node(BaseModel):
    id: str; kind: str; name: str; repo: str
    file: Optional[str] = None; line: Optional[int] = None; end_line: Optional[int] = None
    synthetic: bool = False
    attrs: dict[str, Any] = {}


class Edge(BaseModel):
    id: str; type: str; source: str; target: str
    confidence: str = Field(description="CONFIRMED_STATIC | INFERRED | UNRESOLVED")
    source_file: str; line: int; column: Optional[int] = None
    commit_id: str; repo: str; synthetic: bool = False
    reason: Optional[str] = None; evidence: str = ""; analysis_method: str
    attrs: dict[str, Any] = {}


class GraphMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    generated_at: str; source: str; notice: str
    baseline: Freshness
    repos: dict[str, RepoInfo]
    counts: dict[str, int]


class GraphDoc(BaseModel):
    meta: GraphMeta
    nodes: list[Node]
    edges: list[Edge]


class NodeDetail(BaseModel):
    node: Node
    depends_on: list[Edge]
    depended_on_by: list[Edge]


class Hop(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    edge_id: str; type: str; confidence: str
    from_: str = Field(alias="from"); to: str
    from_name: str; to_name: str; from_kind: str; to_kind: str
    repo: str; file: str; line: int; evidence: str = ""
    reason: Optional[str] = None; commit: str; synthetic: bool; method: str
    attrs: dict[str, Any] = {}


class Trace(BaseModel):
    start: str; direction: str; max_depth: int
    truncated: bool = Field(description="true when more than 200 paths exist; only the first 200 are returned")
    paths: list[list[Hop]]


class ReportEntry(BaseModel):
    name: str; md: str; json_: Optional[str] = Field(None, alias="json"); modified: str
    summary: Optional[dict[str, Any]] = None
    model_config = ConfigDict(populate_by_name=True)


class Reports(BaseModel):
    reports: list[ReportEntry]


class PrFiles(BaseModel):
    comment: Optional[str] = None
    status: Optional[dict[str, Any]] = None
