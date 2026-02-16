"""Debug logging utilities for chunking operations."""

import inspect
import logging

from ingestion_pipeline.config import settings

logger = logging.getLogger(__name__)
DEBUG_PAGE_NUMBERS = settings.DEBUG_PAGE_NUMBERS


def is_verbose_page_debug(page_number: int, context: str = "") -> bool:
    """Checks if verbose debug logging is enabled for a page and logs notification.

    Args:
        page_number (int): The page number to check.
        context (str): Optional context string to identify the calling location.
            If empty, will auto-detect from call stack.

    Returns:
        bool: True if verbose debugging is enabled for this page, False otherwise.
    """
    if page_number not in DEBUG_PAGE_NUMBERS:
        return False

    # Auto-detect calling context if not provided
    if not context:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_frame = frame.f_back
            module = inspect.getmodule(caller_frame)
            function_name = caller_frame.f_code.co_name
            if module:
                module_name = module.__name__.split(".")[-1]
                context = f"{module_name}:{function_name}"
            else:
                context = function_name

    logger.debug(
        f"[{context}] Extra logging enabled for page {page_number}. To change, update DEBUG_PAGE_NUMBERS in config."
    )
    return True


def log_verbose_page_debug(page_number: int, message: str, context: str = ""):
    """Logs a verbose debug message only if debugging is enabled for the page.

    Convenience function that combines the check and logging in one call.

    Args:
        page_number (int): The page number to check.
        message (str): The debug message to log if verbose debugging is enabled.
        context (str): Optional context string to identify the calling location.
            If empty, will auto-detect from call stack.
    """
    if page_number not in DEBUG_PAGE_NUMBERS:
        return

    # Auto-detect calling context if not provided
    if not context:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_frame = frame.f_back
            module = inspect.getmodule(caller_frame)
            function_name = caller_frame.f_code.co_name
            if module:
                module_name = module.__name__.split(".")[-1]
                context = f"{module_name}:{function_name}"
            else:
                context = function_name

    logger.debug(f"[{context}] {message}")
