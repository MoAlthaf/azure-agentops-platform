#Azure opentelemetry integration

import os
import logging
from azure.monitor.opentelemetry import configure_azure_monitor


#Create a logger
logger=logging.getLogger("brand-guardian-telemetry")

def setup_telemetry():
    '''
    Initializes Azure Monitor telemetry for the application.
    Tracks logs, metrics, and traces for monitoring and diagnostics.
    Sends this data to azure monitor.
    '''

    connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

    if not connection_string:
        logger.warning("Azure Monitor connection string not found. Telemetry will not be sent.")
        return
    try:
        configure_azure_monitor(
            connection_string=connection_string,
            logger_name="brand-guardian-telemetry",
        )
        logger.info("Azure Monitor telemetry configured successfully.")
    except Exception as e:
        logger.error(f"Failed to configure Azure Monitor telemetry: {e}")
