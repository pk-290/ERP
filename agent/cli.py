"""
Interactive Command Line Interface for testing the ERP Graph Agent.
Uses Rich for beautiful terminal formatting.
"""
import sys
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
except ImportError:
    print("Please install rich: pip install rich")
    sys.exit(1)

from agent.service import ask_erp_agent, clear_session

console = Console()

def run_cli():
    console.print(Panel.fit("[bold blue]ERP Graph AI Agent[/bold blue]\nType 'exit' to quit, 'clear' to reset history.", border_style="blue"))
    
    # Generate a unique session ID for this CLI run
    session_id = str(uuid.uuid4())
    
    while True:
        try:
            query = Prompt.ask("\n[bold green]You[/bold green]")
            query = query.strip()
            
            if not query:
                continue
            if query.lower() in ('exit', 'quit'):
                break
            if query.lower() == 'clear':
                clear_session(session_id)
                console.print("[dim]Conversation history cleared.[/dim]")
                continue
                
            with console.status("[bold yellow]Agent is thinking and querying Kuzu...[/bold yellow]"):
                # Call the service layer, which maintains state and runs ReAct
                response = ask_erp_agent(session_id, query)
                
            console.print("\n[bold purple]ERP Agent:[/bold purple]")
            console.print(Markdown(response))
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {str(e)}[/red]")

if __name__ == "__main__":
    run_cli()
