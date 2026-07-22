# AI System

The AI system is not implemented in this foundation. The architecture reserves space for a future assistant that can interpret user intent, retrieve candidate offers, rank results, and explain recommendations.
Current staging explanations are rule-based search metadata, not model-generated recommendations.

## Intended Responsibilities

- Parse shopping intent and constraints.
- Retrieve relevant products and offers.
- Use vector search for semantic matching when appropriate.
- Rank recommendations using transparent signals.
- Explain tradeoffs without inventing facts.

## Guardrails

- Ground recommendations in stored offer data.
- Clearly separate model-generated explanation from provider facts.
- Do not claim live price or availability unless recently verified.
- Avoid scraping as a data acquisition strategy.
- Log recommendation inputs and outputs for evaluation.

## Future Modules

- Intent classification
- Retrieval orchestration
- Ranking policies
- Recommendation trace storage
- Evaluation harness
