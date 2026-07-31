import operator
from typing import List,Annotated,Dict,Optional,Any,TypedDict



class ComplianceIssue(TypedDict):
    category: str
    description: str
    severity: str
    timestamp: Optional[str]

class VideoAuditState(TypedDict):

    #input params
    video_url:str
    video_id:str

    #ingestion and extraction data
    local_file_path: str
    video_metadata: Dict[str,Any]
    transcript: Optional[str]
    ocr_text: List[str]

    #analysis output
    compliance_results: Annotated[List[ComplianceIssue],operator.add]

    #final deliverables
    final_status: str 
    final_report: str

    #system observability
    # errors: API timeouts, system level errors ,etc
    errors: Annotated[List[str],operator.add]


