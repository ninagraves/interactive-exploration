"""Shared fixtures: the running example log."""

from pathlib import Path

import pytest
from ocelescope import OCEL

#: Folder of the running example (a copy of the running example of the location-based OCPM project).
EXAMPLE = Path(__file__).parents[3] / "data" / "running_example"


@pytest.fixture(scope="session")
def ocel() -> OCEL:
    """The running example log: one slab s1, five coils c1 to c5, 17 events."""
    return OCEL.read(EXAMPLE / "running_example.sqlite")
