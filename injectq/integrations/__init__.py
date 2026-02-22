import logging

from .fastapi import InjectAPI, InjectFastAPI, InjectQRequestMiddleware, setup_fastapi
from .fastmcp import InjectMCP, InjectQMCPMiddleware, setup_mcp
from .taskiq import InjectTask, InjectTaskiq, setup_taskiq


_logger = logging.getLogger("injectq.integrations")


__all__ = [
    "InjectAPI",
    "InjectFastAPI",
    "InjectMCP",
    "InjectQMCPMiddleware",
    "InjectQRequestMiddleware",
    "InjectTask",
    "InjectTaskiq",
    "setup_fastapi",
    "setup_mcp",
    "setup_taskiq",
]
