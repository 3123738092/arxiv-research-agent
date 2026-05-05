"""Stage 7: Pydantic schema validation for all output files.

Validates all data before writing to shared_data/.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, field_validator


class AuthorRecord(BaseModel):
    author_id: str
    name: str
    s2_author_id: Optional[str] = None
    affiliation_ids: List[str] = []
    paper_ids: List[str] = []


class AffiliationRecord(BaseModel):
    affiliation_id: str
    name: str
    country: Optional[str] = None


class PaperRecord(BaseModel):
    arxiv_id: str
    arxiv_id_versioned: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    authors_raw: List[str] = []
    author_ids: List[str] = []
    published: Optional[str] = None
    updated: Optional[str] = None
    arxiv_url: Optional[str] = None
    pdf_url: Optional[str] = None
    categories: List[str] = []
    primary_category: Optional[str] = None
    comment: Optional[str] = None
    journal_ref: Optional[str] = None
    doi: Optional[str] = None
    source: str = "arxiv"
    s2_paper_id: Optional[str] = None
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None
    year: Optional[int] = None
    venue: Optional[dict] = None
    open_access_pdf: Optional[str] = None
    embedding_row: Optional[int] = None
    code_url: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()


class CitationEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    to: str


class CoauthorshipEdge(BaseModel):
    author_a: str
    author_b: str
    weight: int


class AuthorPaperEdge(BaseModel):
    author_id: str
    paper_id: str


class ManifestRecord(BaseModel):
    run_id: str
    timestamp: str
    params: dict
    source_status: dict
    counts: dict
    errors: List[str] = []
    warnings: List[str] = []


def validate_papers(papers):
    errors = []
    valid = []
    for i, p in enumerate(papers):
        try:
            valid.append(PaperRecord(**p).model_dump())
        except Exception as e:
            errors.append(f"Paper[{i}] validation failed: {e}")
    return valid, errors


def validate_authors(authors):
    errors = []
    valid = []
    for i, a in enumerate(authors):
        try:
            valid.append(AuthorRecord(**a).model_dump())
        except Exception as e:
            errors.append(f"Author[{i}] validation failed: {e}")
    return valid, errors


def validate_citation_edges(edges):
    errors = []
    valid = []
    for i, e in enumerate(edges):
        try:
            valid.append(CitationEdge(**{"from": e["from"], "to": e["to"]}).model_dump(by_alias=True))
        except Exception as err:
            errors.append(f"CitationEdge[{i}] validation failed: {err}")
    return valid, errors


def validate_coauthorship_edges(edges):
    errors = []
    valid = []
    for i, e in enumerate(edges):
        try:
            valid.append(CoauthorshipEdge(**e).model_dump())
        except Exception as err:
            errors.append(f"CoauthorshipEdge[{i}] validation failed: {err}")
    return valid, errors


def validate_author_paper_edges(edges):
    errors = []
    valid = []
    for i, e in enumerate(edges):
        try:
            valid.append(AuthorPaperEdge(**e).model_dump())
        except Exception as err:
            errors.append(f"AuthorPaperEdge[{i}] validation failed: {err}")
    return valid, errors


def validate_all(papers, authors, affiliations, edges):
    """Run all validations, return (validated_data, all_errors)."""
    all_errors = []

    v_papers, e = validate_papers(papers)
    all_errors.extend(e)

    v_authors, e = validate_authors(authors)
    all_errors.extend(e)

    v_citations, e = validate_citation_edges(edges.get("citations", []))
    all_errors.extend(e)

    v_coauthor, e = validate_coauthorship_edges(edges.get("coauthorship", []))
    all_errors.extend(e)

    v_ap, e = validate_author_paper_edges(edges.get("author_paper", []))
    all_errors.extend(e)

    validated = {
        "papers": v_papers,
        "authors": v_authors,
        "affiliations": affiliations or [],
        "edges": {
            "citations": v_citations,
            "coauthorship": v_coauthor,
            "author_paper": v_ap,
            "citations_external": edges.get("citations_external", []),
        },
    }
    return validated, all_errors
