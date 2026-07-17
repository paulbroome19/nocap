"""Orchestration logic: workflow configs and the Run lifecycle.

`workflows` is the ONLY package that knows the pipeline sequence; it may import
from any stage. Stages never import each other. Empty scaffold.
"""
