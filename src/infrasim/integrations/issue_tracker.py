"""Issue tracker integrations for ChaosProof -- Jira and Linear."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class JiraClient:
    """Client for Jira REST API -- create issues from simulation findings."""

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.project_key = project_key

    async def create_issue(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Bug",
        priority: str = "High",
        labels: list[str] | None = None,
    ) -> dict:
        """Create a Jira issue for a critical/high simulation finding."""
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                "priority": {"name": priority},
                "labels": labels or ["chaosproof", "auto-generated"],
            }
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/rest/api/2/issue",
                auth=(self.email, self.api_token),
                json=payload,
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()


class LinearClient:
    """Client for Linear GraphQL API -- create issues from simulation findings."""

    def __init__(self, api_key: str, team_id: str) -> None:
        self.api_key = api_key
        self.team_id = team_id
        self.base_url = "https://api.linear.app/graphql"

    async def create_issue(
        self,
        title: str,
        description: str = "",
        priority: int = 2,
        labels: list[str] | None = None,
    ) -> dict:
        """Create a Linear issue for a critical/high simulation finding.

        Priority: 0=none, 1=urgent, 2=high, 3=medium, 4=low.
        """
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                }
            }
        }
        """
        variables = {
            "input": {
                "teamId": self.team_id,
                "title": title,
                "description": description,
                "priority": priority,
            }
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.base_url,
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"query": mutation, "variables": variables},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()
