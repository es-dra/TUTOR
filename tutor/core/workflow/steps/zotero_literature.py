"""Zotero Literature Step - Search and load papers from Zotero library.

Integrates ZoteroClient into IdeaFlow to enrich literature analysis
with papers from the user's personal Zotero library.

Usage in workflow config:
    steps:
      - name: zotero_literature
        keywords: ["machine learning", "reinforcement learning"]
        max_results: 10
        item_types: ["journalArticle", "conferencePaper"]
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from tutor.core.workflow.base import WorkflowStep, WorkflowContext
from tutor.core.external.zotero import ZoteroClient, ZoteroAPIError
from tutor.core.workflow.paper_parser import PaperMetadata

logger = logging.getLogger(__name__)


class ZoteroLiteratureStep(WorkflowStep):
    """Search and load papers from Zotero library.

    Searches the user's Zotero library for relevant papers based on
    research keywords and converts them to PaperMetadata format.

    Configuration:
        keywords: List[str] - Search keywords/phrases
        max_results: int - Maximum papers to retrieve (default: 10)
        item_types: List[str] - Filter by Zotero item types
        api_key: str - Zotero API key (or env ZOTERO_API_KEY)
        library_id: str - Zotero library ID (or env ZOTERO_LIBRARY_ID)
        library_type: str - "user" or "group" (default: user)

    State output:
        - zotero_papers: List[PaperMetadata] - Papers from Zotero
        - zotero_errors: List[Dict] - Any search/load errors
        - zotero_query: str - The query that was used
    """

    def __init__(
        self,
        keywords: Optional[List[str]] = None,
        max_results: int = 10,
        item_types: Optional[List[str]] = None,
        api_key: Optional[str] = None,
        library_id: Optional[str] = None,
        library_type: str = "user",
    ):
        super().__init__(
            name="zotero_literature",
            description="Search and load papers from Zotero personal library",
        )
        self.keywords = keywords or []
        self.max_results = max_results
        self.item_types = item_types or ["journalArticle", "conferencePaper", "preprint"]
        self._client: Optional[ZoteroClient] = None
        self._client_config = {
            "api_key": api_key,
            "library_id": library_id,
            "library_type": library_type,
        }

    def _get_client(self) -> Optional[ZoteroClient]:
        """Get or create Zotero client from env/config."""
        if self._client is not None:
            return self._client

        api_key = (
            self._client_config.get("api_key")
            or os.environ.get("ZOTERO_API_KEY")
        )
        library_id = (
            self._client_config.get("library_id")
            or os.environ.get("ZOTERO_LIBRARY_ID")
        )
        library_type = self._client_config.get("library_type", "user")

        if not api_key or not library_id:
            logger.warning(
                "Zotero not configured: set ZOTERO_API_KEY and ZOTERO_LIBRARY_ID"
            )
            return None

        self._client = ZoteroClient(
            api_key=api_key,
            library_id=library_id,
            library_type=library_type,
        )
        return self._client

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        """Search Zotero library and load matching papers.

        Returns:
            {
                "zotero_papers": [PaperMetadata, ...],
                "zotero_errors": [{"keyword": str, "error": str}, ...],
                "zotero_query": str,
                "total_found": int,
                "total_loaded": int,
            }
        """
        # Get keywords from config or context
        keywords = self.keywords or context.get_state("research_keywords", [])
        if not keywords:
            # Try literature_analysis context
            analysis = context.get_state("literature_analysis", {})
            gaps = analysis.get("analysis", {}).get("gaps", [])
            questions = analysis.get("analysis", {}).get("research_questions", [])
            keywords = [g[:50] for g in gaps[:3]] + [q[:50] for q in questions[:2]]

        if not keywords:
            logger.warning("No Zotero keywords provided, skipping")
            return {
                "zotero_papers": [],
                "zotero_errors": [],
                "zotero_query": "",
                "total_found": 0,
                "total_loaded": 0,
            }

        client = self._get_client()
        if not client:
            return {
                "zotero_papers": [],
                "zotero_errors": [{"keyword": kw, "error": "Zotero not configured"}
                                  for kw in keywords],
                "zotero_query": " ".join(keywords),
                "total_found": 0,
                "total_loaded": 0,
            }

        all_papers: List[PaperMetadata] = []
        all_errors: List[Dict[str, str]] = []
        seen_keys: set = set()

        for keyword in keywords:
            try:
                items = client.search_items(
                    query=keyword,
                    limit=self.max_results,
                )
                logger.info(f"Zotero search '{keyword}': {len(items)} results")

                for item in items:
                    data = item.get("data", {})
                    item_key = data.get("key")
                    if not item_key or item_key in seen_keys:
                        continue
                    if data.get("itemType") in ("attachment", "note"):
                        continue

                    seen_keys.add(item_key)

                    # Extract metadata
                    authors = self._extract_authors(data)
                    title = data.get("title", "Untitled")
                    abstract = data.get("abstractNote", "")
                    doi = data.get("DOI", "")
                    url = data.get("url", "")
                    arxiv_id = self._extract_arxiv_id(data)

                    paper = PaperMetadata(
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        source="zotero",
                        url=url or (f"https://doi.org/{doi}" if doi else None),
                        raw_text=self._build_raw_text(data),
                    )
                    all_papers.append(paper)

            except ZoteroAPIError as e:
                logger.error(f"Zotero API error for keyword '{keyword}': {e}")
                all_errors.append({"keyword": keyword, "error": str(e)})
            except Exception as e:
                logger.error(f"Error processing Zotero result for '{keyword}': {e}")
                all_errors.append({"keyword": keyword, "error": str(e)})

        # Store in context
        existing_papers = context.get_state("papers", [])
        context.set_state("papers", existing_papers + all_papers)

        result = {
            "zotero_papers": [p.to_dict() for p in all_papers],
            "zotero_errors": all_errors,
            "zotero_query": " ".join(keywords),
            "total_found": len(all_papers),
            "total_loaded": len(all_papers),
        }

        logger.info(f"Zotero literature step: {len(all_papers)} papers loaded")
        return result

    def _extract_authors(self, data: Dict) -> List[str]:
        authors = []
        for creator in data.get("creators", []):
            if creator.get("creatorType") == "author":
                first = creator.get("firstName", "")
                last = creator.get("lastName", "")
                if last:
                    name = f"{last}" + (f", {first[0]}." if first else "")
                    authors.append(name)
        return authors

    def _extract_arxiv_id(self, data: Dict) -> Optional[str]:
        url = data.get("url", "")
        if "arxiv.org" in url:
            import re
            match = re.search(r'arxiv\.org/(?:abs|pdf)/([0-9.]+)', url)
            if match:
                return match.group(1)
        return None

    def _build_raw_text(self, data: Dict) -> str:
        """Build a text representation from Zotero metadata."""
        lines = []
        if title := data.get("title"):
            lines.append(f"Title: {title}")
        if abstract := data.get("abstractNote"):
            lines.append(f"Abstract: {abstract}")
        if tags := data.get("tags"):
            lines.append(f"Tags: {', '.join(t.get('tag', '') for t in tags)}")
        if doi := data.get("DOI"):
            lines.append(f"DOI: {doi}")
        if date := data.get("date"):
            lines.append(f"Date: {date}")
        if publication := data.get("publicationTitle"):
            lines.append(f"Publication: {publication}")
        return "\n".join(lines)

    def validate(self, context: WorkflowContext) -> List[str]:
        """Validate step prerequisites.

        ZoteroLiteratureStep is designed to run BEFORE literature_analysis in IdeaFlow,
        so we cannot require keywords from literature_analysis to be available.
        The step will skip gracefully in execute() if no keywords are available.

        Only error if Zotero is configured AND no keywords provided AND cannot get from context.
        """
        errors = []

        # Check if Zotero is configured
        client = self._get_client()

        if client and not self.keywords:
            # Zotero is configured but no keywords in config
            # Try to get from context (research_keywords or literature_analysis)
            research_keywords = context.get_state("research_keywords", [])
            analysis = context.get_state("literature_analysis", {})
            gaps = analysis.get("analysis", {}).get("gaps", []) if analysis else []

            if not research_keywords and not gaps:
                # Zotero is configured but we can't find keywords anywhere
                # This is NOT an error - the step will skip gracefully in execute()
                # But we log a warning for visibility
                logger.info(
                    "ZoteroLiteratureStep: Zotero configured but no keywords available. "
                    "Step will skip. Provide keywords in config or ensure "
                    "literature_analysis has run."
                )

        # If Zotero is not configured, skip validation (execute will skip gracefully)
        return errors


__all__ = ["ZoteroLiteratureStep"]
