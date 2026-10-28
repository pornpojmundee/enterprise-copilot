# Relevance gate calibration

Embedder: BAAI/bge-m3

| id | kind | role | should answer | best sim | best BM25 | restricted top match | gate (recommended) |
|---|---|---|---|---|---|---|---|
| G05 | off-topic | employee | no | 0.332 | 2.87 |  | block |
| G06 | off-topic | employee | no | 0.376 | 0.00 |  | block |
| G09 | off-topic | employee | no | 0.390 | 0.00 |  | block |
| G07 | off-topic | employee | no | 0.395 | 3.47 |  | block |
| G08 | off-topic | employee | no | 0.421 | 1.93 |  | block |
| G03 | restricted | employee | no | 0.461 | 2.31 | yes | block |
| G01 | restricted | employee | no | 0.478 | 3.94 | yes | block |
| G02 | restricted | employee | no | 0.485 | 3.97 | yes | block |
| G04 | restricted | employee | no | 0.501 | 3.27 | yes | block |
| R05 | uc2 | employee | yes | 0.528 | 6.46 |  | pass |
| R02 | paraphrase | employee | yes | 0.586 | 5.70 |  | pass |
| R16 | paraphrase | employee | yes | 0.591 | 10.73 |  | pass |
| R04 | keyword | employee | yes | 0.592 | 9.56 |  | pass |
| R11 | keyword | employee | yes | 0.622 | 10.71 |  | pass |
| R17 | rbac-allowed | hr | yes | 0.625 | 11.02 |  | pass |
| G10 | rbac-allowed | hr | yes | 0.625 | 11.02 |  | pass |
| R01 | keyword | employee | yes | 0.658 | 9.41 |  | pass |
| R15 | sec4 | employee | yes | 0.658 | 10.50 |  | pass |
| R10 | paraphrase | employee | yes | 0.659 | 11.89 |  | pass |
| R12 | sec5 | employee | yes | 0.669 | 6.65 |  | pass |
| R07 | paraphrase | employee | yes | 0.674 | 12.83 |  | pass |
| R03 | uc1 | employee | yes | 0.675 | 22.04 |  | pass |
| R06 | keyword | employee | yes | 0.695 | 14.30 |  | pass |
| R14 | keyword | employee | yes | 0.704 | 14.00 |  | pass |
| R20 | keyword | employee | yes | 0.726 | 10.55 |  | pass |
| R08 | keyword | employee | yes | 0.735 | 12.06 |  | pass |
| R09 | uc3 | employee | yes | 0.737 | 8.19 |  | pass |
| R13 | keyword | employee | yes | 0.744 | 8.80 |  | pass |

Recommended: RAG_MIN_SIMILARITY=0.5  RAG_MIN_BM25=4.5
Answerable questions blocked: none
Should-block questions that still reach the LLM: none
