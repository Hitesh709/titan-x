from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from coding_agent import __version__
from coding_agent.agent import Agent
from coding_agent.config import AgentConfig

app = typer.Typer(
    name="coding-agent",
    help="CLI coding assistant powered by LLM",
    add_completion=False,
)
console = Console()


@app.callback()
def callback():
    pass


@app.command()
def run(
    query: str = typer.Argument(..., help="The query to ask the coding agent"),
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider (openai, anthropic)"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model name"),
    workspace: str = typer.Option(None, "--workspace", "-w", help="Working directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
):
    """Run a single query and get a response."""
    config = _build_config(provider, model, workspace, verbose)
    agent = Agent(config=config)

    async def _run():
        response = await agent.run(query, stream=True)
        console.print(Markdown(response))

    asyncio.run(_run())


@app.command()
def chat(
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider (openai, anthropic)"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model name"),
    workspace: str = typer.Option(None, "--workspace", "-w", help="Working directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output"),
    system_prompt: str = typer.Option(None, "--system", "-s", help="Path to custom system prompt file"),
):
    """Start an interactive chat session with the coding agent."""
    config = _build_config(provider, model, workspace, verbose)

    if system_prompt:
        prompt_path = Path(system_prompt)
        if prompt_path.exists():
            config.system_prompt = prompt_path.read_text(encoding="utf-8")

    agent = Agent(config=config)

    console.print(
        Panel.fit(
            f"[bold cyan]Coding Agent v{__version__}[/]\n"
            f"Provider: {config.llm_provider} | Model: {config.llm_model}\n"
            f"Workspace: {config.workspace}\n"
            "Type [bold red]/exit[/] to quit, [bold yellow]/reset[/] to clear history",
            title="Coding Agent",
        )
    )

    while True:
        try:
            query = Prompt.ask("\n[bold green]You[/]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/]")
            break

        if not query.strip():
            continue

        if query.strip() == "/exit":
            break

        if query.strip() == "/reset":
            agent.reset()
            console.print("[yellow]Conversation reset.[/]")
            continue

        console.print("[bold blue]Agent[/]")
        try:
            response = asyncio.run(agent.run(query, stream=True))
            console.print(Markdown(response))
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")


@app.command()
def version():
    """Show the version."""
    console.print(f"Coding Agent v{__version__}")


def _build_config(
    provider: str | None,
    model: str | None,
    workspace: str | None,
    verbose: bool,
) -> AgentConfig:
    config = AgentConfig()
    if provider:
        config.llm_provider = provider
    if model:
        config.llm_model = model
    if workspace:
        config.workspace = Path(workspace)
    config.verbose = verbose
    return config


def main():
    app()
