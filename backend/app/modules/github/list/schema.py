"""Request / response schemas for github.list."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepoItem(BaseModel):
    id: int
    full_name: str
    name: str
    owner: str
    private: bool
    description: str | None = None
    default_branch: str = "main"
    html_url: str
    clone_url: str
    language: str | None = None
    updated_at: str | None = None


class ListReposResponse(BaseModel):
    items: list[RepoItem] = Field(default_factory=list)
    page: int = 1
    per_page: int = 50
    total: int | None = None
    message: str = "GitHub repositories"


class RepoCountResponse(BaseModel):
    total: int = 0
    message: str = "GitHub repository count"


class BranchItem(BaseModel):
    name: str
    protected: bool = False
    commit_sha: str | None = None


class ListBranchesResponse(BaseModel):
    owner: str
    repo: str
    default_branch: str | None = None
    items: list[BranchItem] = Field(default_factory=list)
    message: str = "Repository branches"


# Scaffold aliases
class ListRequest(BaseModel):
    pass


class ListResponse(ListReposResponse):
    pass
