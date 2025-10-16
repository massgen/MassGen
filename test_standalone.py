# -*- coding: utf-8 -*-
"""Standalone test to check pytest warnings."""


def test_simple():
    """Simple test."""
    assert 1 + 1 == 2


def test_another():
    """Another test."""
    assert "hello".upper() == "HELLO"
