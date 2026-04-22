import re
from pathlib import Path

app_path = Path("agent_terminal_ui/app.py")
content = app_path.read_text()

replacement = """        try:
            from pathlib import Path
            logo_path = Path(__file__).parent / "tui" / "logo.txt"
            logo_str = logo_path.read_text()
            logo = (
                f"{logo_str}\\n[bold white]Welcome to Agent Terminal UI[/bold white]"
                "\\nType [cyan]/help[/cyan] to see available commands or "
                "[cyan]/plan[/cyan] to start planning.\\n"
            )
        except Exception:
            logo = (
                "[bold white]Welcome to Agent Terminal UI[/bold white]\\n"
                "Type [cyan]/help[/cyan] to see available commands or "
                "[cyan]/plan[/cyan] to start planning.\\n"
            )
"""

content = re.sub(
    r"        logo = \(\n.*?\n        \)", replacement, content, flags=re.DOTALL
)

app_path.write_text(content)
