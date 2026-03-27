import sys
from loguru import logger

logger.remove()

logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}"
)

logger.add(
    "logs/policyguard.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG"
)