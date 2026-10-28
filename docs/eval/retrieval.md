# Retrieval evaluation (Knowledge agent)

Embedder: BAAI/bge-m3 · golden set: 20 questions · 2026-10-28

| mode | hit@1 | hit@3 | hit@5 | MRR | RBAC leaks |
|---|---|---|---|---|---|
| bm25 | 0.83 | 1.00 | 1.00 | 0.92 | 0 |
| vector | 0.94 | 1.00 | 1.00 | 0.97 | 0 |
| hybrid | 0.94 | 1.00 | 1.00 | 0.97 | 0 |

Hybrid — not ranked #1:
- R05 (uc2): rank 2 · top3 ['HR-003#3', 'HR-001#6', 'HR-001#3.3']
