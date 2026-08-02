import uuid
import logging
from fastapi import FastAPI,HTTPException
from starlette.concurrency import run_in_threadpool

from pydantic import BaseModel
from typing import List

from dotenv import load_dotenv
load_dotenv(override=True)

from backend.src.api.telemetry import setup_telemetry
setup_telemetry()

#import workflow graph
from backend.src.graph.workflow import app as compliance_graph

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger=logging.getLogger("brand-guardian-api")

app=FastAPI(title="Brand Guardian API",
    description="API for managing brand compliance"
    ,version="1.0.0")


class AuditRequest(BaseModel):
    '''
    Request model for initiating a video compliance audit.
    '''
    video_url: str

class ComplianceIssue(BaseModel):
    '''
    Model representing a compliance issue detected in the video.
    '''
    severity: str
    category: str
    description: str

class AuditResponse(BaseModel):
    '''
    Response model for the results of a video compliance audit.
    '''
    session_id: str
    video_id: str
    status: str
    final_report: str
    compliance_results: List[ComplianceIssue]
    errors: List[str]

@app.post("/audit",response_model=AuditResponse)
async def audit_video(request:AuditRequest):
    '''
    Endpoint to initiate a video compliance audit.
    '''
    session_id=str(uuid.uuid4())
    video_id=f"vid_{session_id[:8]}"
    logger.info(f"Received audit request for video: {request.video_url} with session ID: {session_id}")

    initial_inputs={
        "video_url":request.video_url,
        "video_id":video_id,
        "compliance_results": [],
        "errors":[]
    }

    try:
        final_state=await run_in_threadpool(compliance_graph.invoke, initial_inputs)
        return AuditResponse(
            session_id=session_id,
            video_id=final_state.get("video_id"),
            status=final_state.get("final_status"),
            final_report=final_state.get("final_report","No report generated"),
            compliance_results=[
                ComplianceIssue(
                    severity=issue.get("severity"),
                    category=issue.get("category"),
                    description=issue.get("description")
                ) for issue in final_state.get("compliance_results",[])
            ],
            errors=final_state.get("errors",[])
        )
    except Exception as e:
        logger.error(f"Audit failed for session {session_id}: {e}")
        raise HTTPException(status_code=500,detail=f"Audit failed: {str(e)}")

@app.get("/health")
async def health_check():
    '''
    Health check endpoint to verify that the API is running.
    '''
    return {"status":"ok"}
