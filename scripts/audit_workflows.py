#!/usr/bin/env python3
"""Audit GitHub Actions workflows for a list of repositories.

The script queries the GitHub API for workflow run status and scans each
workflow file for secret/variable references. It requires the
``GITHUB_TOKEN`` environment variable to be set with a token that has
``repo`` and ``workflow`` scopes.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import requests

API_ROOT = "https://api.github.com"


@dataclass
class WorkflowRunSummary:
    name: str
    path: str
    url: Optional[str]
    status: Optional[str]
    conclusion: Optional[str]
    failure_step: Optional[str]
    failure_details: Optional[str]


@dataclass
class RepoAudit:
    repo: str
    workflows: List[WorkflowRunSummary] = field(default_factory=list)
    secrets: Dict[str, List[str]] = field(default_factory=lambda: {"secrets": [], "vars": []})
    default_workflow_permissions: Optional[str] = None
    can_approve_pr_reviews: Optional[bool] = None


def github_request(token: str, method: str, path: str, **kwargs) -> requests.Response:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers["Accept"] = "application/vnd.github+json"
    response = requests.request(method, f"{API_ROOT}{path}", headers=headers, timeout=30, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub API request failed for {path}: {response.status_code} {response.text}")
    return response


def list_workflows(token: str, repo: str) -> Iterable[dict]:
    response = github_request(token, "GET", f"/repos/{repo}/actions/workflows")
    data = response.json()
    return data.get("workflows", [])


def latest_run(token: str, repo: str, workflow_id: int) -> Optional[dict]:
    response = github_request(
        token,
        "GET",
        f"/repos/{repo}/actions/workflows/{workflow_id}/runs",
        params={"per_page": 1},
    )
    runs = response.json().get("workflow_runs", [])
    return runs[0] if runs else None


def summarize_failure_step(token: str, repo: str, run_id: int) -> tuple[Optional[str], Optional[str]]:
    response = github_request(
        token,
        "GET",
        f"/repos/{repo}/actions/runs/{run_id}/jobs",
        params={"per_page": 1},
    )
    jobs = response.json().get("jobs", [])
    if not jobs:
        return None, None

    steps = jobs[0].get("steps", [])
    for step in steps:
        if step.get("conclusion") == "failure":
            return step.get("name"), step.get("completed_at")
    return None, None


def fetch_workflow_content(token: str, repo: str, path: str) -> str:
    response = github_request(token, "GET", f"/repos/{repo}/contents/{path}")
    data = response.json()
    if isinstance(data, list):
        raise RuntimeError(f"Expected file but found directory for {path}")
    content = data.get("content", "")
    encoding = data.get("encoding")
    if encoding != "base64":
        raise RuntimeError(f"Unexpected encoding for {path}: {encoding}")
    return base64.b64decode(content).decode("utf-8", errors="replace")


SECRET_PATTERN = re.compile(r"\$\{\{\s*(secrets|vars)\.([A-Za-z0-9_]+)\s*}}")


def extract_secret_references(text: str) -> Dict[str, List[str]]:
    discovered: Dict[str, set[str]] = {"secrets": set(), "vars": set()}
    for match in SECRET_PATTERN.finditer(text):
        prefix, name = match.groups()
        discovered[prefix].add(name)
    return {key: sorted(values) for key, values in discovered.items()}


def merge_secret_maps(destination: Dict[str, List[str]], source: Dict[str, List[str]]) -> None:
    for key, values in source.items():
        existing = set(destination.get(key, []))
        existing.update(values)
        destination[key] = sorted(existing)


def get_workflow_permissions(token: str, repo: str) -> tuple[Optional[str], Optional[bool]]:
    response = github_request(token, "GET", f"/repos/{repo}/actions/permissions")
    data = response.json()
    return data.get("default_workflow_permissions"), data.get("can_approve_pull_request_reviews")


def audit_repo(token: str, repo: str) -> RepoAudit:
    audit = RepoAudit(repo=repo)
    workflows = list_workflows(token, repo)

    for workflow in workflows:
        run = latest_run(token, repo, workflow["id"])
        failure_step = None
        failure_details = None
        url = run.get("html_url") if run else None
        status = run.get("status") if run else None
        conclusion = run.get("conclusion") if run else None
        if run and conclusion == "failure":
            failure_step, failure_details = summarize_failure_step(token, repo, run["id"])

        audit.workflows.append(
            WorkflowRunSummary(
                name=workflow.get("name", "unknown"),
                path=workflow.get("path", ""),
                url=url,
                status=status,
                conclusion=conclusion,
                failure_step=failure_step,
                failure_details=failure_details,
            )
        )

        if workflow.get("path"):
            content = fetch_workflow_content(token, repo, workflow["path"])
            merge_secret_maps(audit.secrets, extract_secret_references(content))

    default_permissions, can_approve = get_workflow_permissions(token, repo)
    audit.default_workflow_permissions = default_permissions
    audit.can_approve_pr_reviews = can_approve

    return audit


def render_markdown(audits: Iterable[RepoAudit]) -> str:
    lines: List[str] = []
    for audit in audits:
        lines.append(f"## {audit.repo}\n")
        lines.append("| Workflow | Status | Conclusion | Failure Step | Details | URL |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for workflow in audit.workflows:
            lines.append(
                "| {name} ({path}) | {status} | {conclusion} | {failure_step} | {failure_details} | [link]({url}) |".format(
                    name=workflow.name,
                    path=workflow.path,
                    status=workflow.status or "-",
                    conclusion=workflow.conclusion or "-",
                    failure_step=workflow.failure_step or "-",
                    failure_details=workflow.failure_details or "-",
                    url=workflow.url or "#",
                )
            )

        lines.append("")
        lines.append("### Referenced secrets and variables")
        if audit.secrets["secrets"] or audit.secrets["vars"]:
            lines.append("- Secrets: " + ", ".join(audit.secrets["secrets"]) if audit.secrets["secrets"] else "- Secrets: none")
            lines.append("- Variables: " + ", ".join(audit.secrets["vars"]) if audit.secrets["vars"] else "- Variables: none")
        else:
            lines.append("No secrets or variables referenced.")

        if audit.default_workflow_permissions:
            permission_text = audit.default_workflow_permissions
        else:
            permission_text = "unknown"
        lines.append("")
        lines.append(f"Default workflow permissions: **{permission_text}**")
        if audit.can_approve_pr_reviews is not None:
            lines.append(
                "Can approve pull request reviews: **{}**".format("yes" if audit.can_approve_pr_reviews else "no")
            )
        lines.append("")

    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit GitHub Actions workflows")
    parser.add_argument(
        "repos",
        nargs="*",
        default=[
            "GaiaEyesHQ/gaiaeyes-ios",
            "GaiaEyesHQ/DataExport",
            "GaiaEyesHQ/gaiaeyes-wp",
        ],
        help="Repositories to audit in the form owner/name.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Optional path to write the Markdown report. Defaults to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN environment variable is required", file=sys.stderr)
        return 1

    audits: List[RepoAudit] = []
    for repo in args.repos:
        try:
            audits.append(audit_repo(token, repo))
        except Exception as exc:  # noqa: BLE001 - Provide context to the caller
            print(f"Failed to audit {repo}: {exc}", file=sys.stderr)

    report = render_markdown(audits)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
