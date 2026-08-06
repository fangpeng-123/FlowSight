# 01 — Landscape: what not to rebuild

Type: research · Status: claimed (charting) · Blocked by: —

## Question

What existing tools and prior art already do codebase knowledge-graph / call-graph / data-flow visualization — especially for Python and LLM-assisted code understanding — and what should FlowSight **reuse vs. rebuild**?

Cover at least: CodeGraph, AppMap, CodeSee, Sourcegraph/Cody, Swimm, jedi, pyright/Pylance, tree-sitter, Semgrep, and any LLM-driven code-graph tools. For each: what it builds (static parse / runtime trace / LLM), what it visualizes, license, embeddability. Goal: a sharp "reuse vs build" list so FlowSight doesn't reinvent wheels.

## Notes

A `/research` subagent is resolving this during charting. Findings land in `../research/landscape.md`.
