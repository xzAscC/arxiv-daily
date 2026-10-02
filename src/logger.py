import sys
from pathlib import Path
from loguru import logger

def setup_logger(debug: bool = False, log_file: str = "logs/app.log") -> None:
    """
    Set up the logger with console and file output.
    
    Args:
        debug: If True, set console log level to DEBUG, otherwise INFO
        log_file: Path to the log file (default: logs/app.log)
    
    Returns:
        None: The logger is configured globally
    """
    # Remove default handler
    logger.remove()
    
    # Console logging
    if debug:
        logger.add(sys.stdout, level="DEBUG", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    else:
        logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    # Error logging to stderr
    logger.add(sys.stderr, level="ERROR", format="<red>{time:YYYY-MM-DD HH:mm:ss}</red> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    
    # File logging with rotation and retention
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        log_file,
        level="DEBUG" if debug else "INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",  # Rotate when file reaches 10MB
        retention="30 days",  # Keep logs for 30 days
        compression="gz",  # Compress rotated logs
        backtrace=True,  # Include full backtrace for exceptions
        diagnose=True,  # Include variable values in backtrace
    )
    
    return logger