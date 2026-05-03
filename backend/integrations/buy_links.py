"""Execution-layer preview links until Jupiter quote API lands (v4)."""

from urllib.parse import quote


def jupiter_solana_buy_url(output_mint: str) -> str:
    """Https URL for Jupiter aggregator UI preview (Phantom web / in-app browse)."""

    mint = quote(output_mint.strip(), safe="")
    return f"https://jup.ag/swap/SOL-{mint}?referrer=cortisol"
