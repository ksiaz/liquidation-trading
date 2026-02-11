#!/usr/bin/env python3
"""
Run Observatory Server Standalone.

Reads from execution.db without requiring the main runtime.
Use this for viewing historical data or debugging.

Usage:
    python scripts/run_observatory.py [--port PORT] [--db PATH]

Examples:
    # Default (port 8080, logs/execution.db)
    python scripts/run_observatory.py

    # Custom port
    python scripts/run_observatory.py --port 9000

    # Custom database path
    python scripts/run_observatory.py --db /path/to/execution.db

API Documentation:
    http://localhost:8080/docs
"""
import argparse
import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)
logger = logging.getLogger('Observatory')


def main():
    parser = argparse.ArgumentParser(
        description='Run Observatory Server (read-only system observation)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8080,
        help='Port to listen on (default: 8080)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--db',
        type=str,
        default='logs/execution.db',
        help='Path to execution.db (default: logs/execution.db)'
    )
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload for development'
    )

    args = parser.parse_args()

    # Check if database exists
    if not os.path.exists(args.db):
        logger.warning(f"Database not found: {args.db}")
        logger.warning("Server will start but queries will return empty results")

    # Import and configure
    from runtime.observatory.server import app, configure

    configure(
        stability_observer=None,  # Not available in standalone mode
        resource_monitor=None,    # Not available in standalone mode
        execution_db=args.db
    )

    logger.info("=" * 60)
    logger.info("OBSERVATORY SERVER (STANDALONE)")
    logger.info("=" * 60)
    logger.info(f"Database: {args.db}")
    logger.info(f"Endpoint: http://{args.host}:{args.port}")
    logger.info(f"API Docs: http://{args.host}:{args.port}/docs")
    logger.info("=" * 60)
    logger.info("Mode: Read-only observation (no execution influence)")
    logger.info("=" * 60)

    # Run server
    import uvicorn
    uvicorn.run(
        "runtime.observatory.server:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == '__main__':
    main()
