import logging
import os
from typing import Any, Dict, Literal, Optional

from langchain_community.vectorstores import AzureSearch
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

from backend.src.graph.state import VideoAuditState
from backend.src.services.video_indexer import VideoIndexerService


logger = logging.getLogger("brand-guardian")


class ComplianceIssueOutput(BaseModel):
    """One rule violation found in the video."""

    category: str = Field(description="The compliance area, such as claim_validation.")
    description: str = Field(description="Why the video violates the rule.")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    timestamp: Optional[str] = Field(
        default=None,
        description="The relevant video timestamp when it is available, for example 00:01:32.",
    )


class AuditOutput(BaseModel):
    """The only output contract accepted from the audit model."""

    compliance_results: list[ComplianceIssueOutput]
    status: Literal["PASS", "FAIL"]
    final_report: str


def _required_env(name: str) -> str:
    """Return a required setting without ever logging its value."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def index_video_node(state: VideoAuditState) -> Dict[str, Any]:
    """Download a YouTube video, index it, and return extracted Video Indexer data."""
    video_url = state.get("video_url", "")
    video_id = state.get("video_id", "vid_demo")
    local_path: Optional[str] = None

    logger.info("[Indexer] Processing video URL: %s", video_url)

    try:
        if "youtube.com" not in video_url and "youtu.be" not in video_url:
            raise ValueError("Please provide a valid YouTube URL")

        vi_service = VideoIndexerService()
        local_path = vi_service.download_youtube_video(
            video_url, output_path="temp_audit_video.mp4"
        )
        azure_video_id = vi_service.upload_video(local_path, video_name=video_id)
        logger.info("[Indexer] Upload succeeded. Azure video ID: %s", azure_video_id)

        raw_insights = vi_service.wait_for_processing(azure_video_id)
        clean_data = vi_service.extract_data(raw_insights)
        logger.info("[Indexer] Extraction complete")
        return clean_data

    except Exception as exc:
        logger.exception("[Indexer] Video Indexer failed")
        return {
            "errors": [str(exc)],
            "final_status": "ERROR",
            "transcript": "",
            "ocr_text": [],
        }
    finally:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)


def audio_content_node(state: VideoAuditState) -> Dict[str, Any]:
    """Retrieve compliance rules and audit transcript/OCR with the OpenAI API."""
    logger.info("[Auditor] Querying the knowledge base and LLM")
    transcript = state.get("transcript") or ""
    ocr_text = state.get("ocr_text") or []

    if not transcript:
        logger.warning("[Auditor] No transcript available; skipping audit")
        return {
            "final_status": "SKIPPED",
            "final_report": "Audit skipped because video processing produced no transcript.",
        }

    try:
        openai_api_key = _required_env("OPENAI_API_KEY")
        chat_model = _required_env("OPENAI_CHAT_MODEL")

        llm = ChatOpenAI(
            api_key=openai_api_key,
            model=chat_model,
            temperature=0,
        )
        structured_llm = llm.with_structured_output(AuditOutput)

        embeddings = OpenAIEmbeddings(
            api_key=openai_api_key,
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
        vector_store = AzureSearch(
            azure_search_endpoint=_required_env("AZURE_SEARCH_ENDPOINT"),
            azure_search_key=_required_env("AZURE_SEARCH_API_KEY"),
            index_name=_required_env("AZURE_SEARCH_INDEX_NAME"),
            embedding_function=embeddings.embed_query,
        )

        ocr_content = "\n".join(ocr_text)
        query_text = f"Transcript:\n{transcript}\n\nOn-screen text:\n{ocr_content}"
        docs = vector_store.similarity_search(query_text, k=3)

        if not docs:
            logger.error("[Auditor] No compliance rules retrieved from the knowledge base index")
            return {
                "errors": [
                    "No compliance rules were retrieved from the Azure AI Search index. "
                    "The audit was not run because it would not be grounded in any rules. "
                    "Check that the index has been populated (see backend/scripts/index_documents.py)."
                ],
                "final_status": "ERROR",
                "final_report": "Audit could not be completed because no compliance rules were found in the knowledge base.",
            }

        retrieved_rules = "\n\n".join(doc.page_content for doc in docs)

        system_prompt = f"""
You are a senior brand compliance auditor. Audit only against the official rules below.

OFFICIAL REGULATORY RULES:
{retrieved_rules}

Instructions:
1. Analyze the transcript and on-screen text.
2. Report every rule violation supported by the supplied evidence.
3. Set status to PASS only when there are no violations; otherwise set it to FAIL.
4. Include a timestamp only when one is present in the provided evidence. Do not invent one.
5. Do not treat system failures or missing rules as compliance violations.
""".strip()
        user_message = f"""
VIDEO METADATA:
{state.get('video_metadata', {})}

TRANSCRIPT:
{transcript}

ON-SCREEN TEXT:
{ocr_content}
""".strip()

        audit_data = structured_llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
        )
        return {
            "compliance_results": [issue.model_dump() for issue in audit_data.compliance_results],
            "final_status": audit_data.status,
            "final_report": audit_data.final_report,
        }

    except Exception as exc:
        logger.exception("[Auditor] System error")
        return {
            "errors": [str(exc)],
            "final_status": "ERROR",
            "final_report": "Audit could not be completed because of a system error.",
        }
