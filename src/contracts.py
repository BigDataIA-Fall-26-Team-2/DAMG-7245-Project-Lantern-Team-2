"""Shared helpers implementing the data shapes in docs/CONTRACTS.md."""


def stem_for(meta: dict) -> str:
    """File stem `{ticker}_{form}_{period}` per CONTRACTS.md's stem convention."""
    form = meta["form"].replace("-", "")
    return f"{meta['ticker']}_{form}_{meta['period']}"
