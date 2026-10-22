# knowledge-os

Knowledge OS Enterprise: recuperação de conhecimento técnico a partir de documentação, especificações, ADRs, código e testes, com respostas que trazem evidências rastreáveis. O Git é a fonte de verdade e todo índice é derivado.

- Especificação (Fase 0): [`docs/fase-0/`](docs/fase-0/README.md)
- Decisões de arquitetura: [`docs/fase-0/05-adrs.md`](docs/fase-0/05-adrs.md)
- Backlog: [`docs/fase-0/08-backlog.md`](docs/fase-0/08-backlog.md)
- CI/CD, merge automático e entrega: [`docs/ci-cd.md`](docs/ci-cd.md)

## Estado

Fase 1 em andamento. Pronto: BL-01 (`kos init`).

## Uso

Requer Python ≥ 3.11 com SQLite compilado com FTS5. Não há dependências externas.

```sh
PYTHONPATH=src python -m kos init            # cria ./.kos/index.sqlite e ./.kos/audit.sqlite
PYTHONPATH=src python -m kos init --json     # saída kos.init.v1
```

Ou instale em modo editável (`pip install -e .`) e use `kos init`.

O diretório dos bancos é `--home`, ou `$KOS_HOME`, ou `./.kos`. `index.sqlite` pode ser apagado e reconstruído; `audit.sqlite` guarda a trilha de auditoria e não deve ser apagado.

## Testes

```sh
PYTHONPATH=src python -m unittest discover -s tests -t .
```

Os testes também conferem que o DDL em `src/kos/store/*.sql` é o mesmo da especificação e que o catálogo de erros é o de CTR-10.
