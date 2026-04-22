#!/usr/bin/env python
"""Headless validation script for the Agent Terminal UI ACP client."""

import asyncio
import logging

from agent_terminal_ui.client import AgentClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tui_validator")


async def main() -> None:
    client = AgentClient(base_url="http://localhost:8000")
    logger.info("Connecting to agent-utilities via tui ACPClient...")

    try:
        session_id = await client.create_session()
        logger.info(f"✅ Created session: {session_id}")
    except Exception as e:
        logger.error(f"❌ Failed to create session: {e}")
        return

    logger.info("Sending /plan prompt...")
    # Use the logic built into client.stream
    # For a direct RPC, we could use client.send_rpc, but stream is the main entrypoint
    has_plan = False

    try:
        # We simulate the UI sending /plan message.
        # Since client.stream() intercepts /plan to set modeId=plan
        async for event in client.stream("/plan list files", session_id=session_id):
            if event.get("type") == "sideband":
                data = event.get("data", {})
                if data.get("type") == "plan":
                    logger.info("✅ Received plan update through stream.")
                    has_plan = True
            elif event.get("type") == "error":
                logger.error(f"❌ Server Error Event: {event.get('message')}")
            elif event.get("type") in ("text", "turn_end"):
                # just passing through
                pass

            if has_plan:
                break

        if not has_plan:
            logger.warning(
                "⚠️ No plan events detected on /plan prompt. "
                "(Might be okay if graph didn't need to plan)."
            )
    except Exception as e:
        logger.error(f"❌ Stream failed: {e}")

    await client.close()
    logger.info("Validation complete.")


if __name__ == "__main__":
    asyncio.run(main())
