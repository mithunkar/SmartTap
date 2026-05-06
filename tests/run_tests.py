#!/usr/bin/env python3
"""Small wrapper for running the retained SmartTap pytest suite."""

from __future__ import annotations

import sys

import pytest


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q"]))
