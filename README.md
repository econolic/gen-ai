# gen-ai

Repository with practical work on Generative AI, Agentic AI, RAG, LangGraph, and context engineering.

## Contents

| Artifact | Format | Purpose |
| --- | --- | --- |
| [context_engineering.ipynb](context_engineering.ipynb) | Jupyter Notebook | Context engineering practice: persona and tone control, feedback triage and listing title/category generation. |
| [todo_agent.ipynb](todo_agent.ipynb) | Jupyter Notebook | TODO agent built with LangGraph v1, tool calling and `InMemoryStore` for task management. |
| [rag_financial_statements_analysis.ipynb](rag_financial_statements_analysis.ipynb) | Jupyter Notebook | RAG system for answering questions about company financial metrics using only the provided context. |
| [tech_support_agent.ipynb](tech_support_agent.ipynb) | Jupyter Notebook | LangGraph tech support agent: request classification, FAQ/RAG search, short response drafting and escalation decision. |
| [excel-agent-platform](excel-agent-platform/) | Full-stack project | AI platform for enriching Excel files with LangGraph, FastAPI, React, MCP tools, live sources and OpenRouter. |

## Notebooks

### Context Engineering

[context_engineering.ipynb](context_engineering.ipynb) contains exercises on designing context for LLMs: controlling role and response style, structured classification of user feedback, and generating listing attributes.

### TODO Agent

[todo_agent.ipynb](todo_agent.ipynb) shows a compact agentic workflow for task management. It focuses on `create_agent`, LangChain tools, LangGraph `InMemoryStore`, and state persistence across agent actions.

### RAG for Financial Statements

[rag_financial_statements_analysis.ipynb](rag_financial_statements_analysis.ipynb) builds a RAG pipeline for financial statements of Ukrainian companies. The notebook uses LangChain, Chroma, OpenAI embeddings, an OpenRouter-compatible chat model, Pydantic configuration, and test questions that verify answers strictly against retrieved context.

### Tech Support Agent

[tech_support_agent.ipynb](tech_support_agent.ipynb) demonstrates a LangGraph v1 workflow for handling support requests. The agent classifies the request, searches relevant FAQ knowledge, drafts a short Ukrainian response, and decides whether escalation is required.


## Excel Agent Platform

[excel-agent-platform](excel-agent-platform/) is the final full-stack project for automated Excel table enrichment. The user uploads a workbook, provides a natural-language task, and the system builds and executes a plan through LangGraph.

Key capabilities:

- live-first enrichment via Wikidata/Wikipedia, Serper fallback, and LLM extraction fallback;
- OpenRouter LLM planner fallback for complex or ambiguous tasks;
- strict tool boundary through FastMCP services;
- safe formula DSL for calculations over Excel columns;
- human-in-the-loop approval before costly web/hybrid enrichment scenarios;
- React + Vite frontend, FastAPI backend, and Docker Compose runtime;
- full evidence pack: lint, unit, contract, integration, e2e, routing eval and performance tests.

Quick start:

```bash
cd excel-agent-platform
cp .env.example .env
docker compose up --build
```

Submission checks:

```bash
cd excel-agent-platform
make eval
make docker-health
```

Detailed documentation, live demo screenshots and submission commands are available in [excel-agent-platform/README.md](excel-agent-platform/README.md).

## Environment Variables

The notebooks and `excel-agent-platform` read secrets from `.env`. Use `.env.example` as the template.
