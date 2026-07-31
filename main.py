'''
Main entry point for the application.
'''

import uuid
import logging
import json

from dotenv import load_dotenv
load_dotenv(override=True)

from backend.src.graph.workflow import app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger=logging.getLogger("brand-guardian-logger")


def run_cli_simulation():
    '''
    Simulates the workflow execution in a CLI environment.
    '''
    session_id=str(uuid.uuid4())
    logger.info(f"Starting workflow simulation with session ID: {session_id}")


    #define the initial state
    initial_inputs={
        "video_url":"https://www.youtube.com/watch?v=zhsAd5ORk1Y",
        "video_id":f"vid_{session_id[:8]}",
        "compliance_results": [],
        "errors":[]
    }

    print("----Initializing Workflow----")
    print(f"Input Payload: {json.dumps(initial_inputs, indent=2)}")

    try:
        final_state=app.invoke(initial_inputs)
        print("----Workflow Completed----")
        print("\n Compliance Audit Report ==")
        print(f"video id: {final_state.get('video_id')}")
        print(f"status: {final_state.get('final_status')}")
        print("\n [VIOLATION DETECTED]")
        results=final_state.get("compliance_results",[])
        if results:
            for issue in results:
                severity = issue.get("severity")
                category = issue.get("category")
                description = issue.get("description")
                print(f" [{severity}] [{category}] {description}")
        else:
            print(" No violations detected.")
        print("\n FINAL SUMMARY")
        print(final_state.get("final_report"))
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        raise e

if __name__=="__main__":
    run_cli_simulation()

