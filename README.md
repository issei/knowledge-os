# knowledge-os

Knowledge OS Enterprise: recuperação de conhecimento técnico a partir de documentação, especificações, ADRs, código e testes, com respostas que trazem evidências rastreáveis. O Git é a fonte de verdade e todo índice é derivado.

- Especificação (Fase 0): [`docs/fase-0/`](docs/fase-0/README.md)
- Decisões de arquitetura: [`docs/fase-0/05-adrs.md`](docs/fase-0/05-adrs.md)
- Backlog: [`docs/fase-0/08-backlog.md`](docs/fase-0/08-backlog.md)
- CI/CD, merge automático e entrega: [`docs/ci-cd.md`](docs/ci-cd.md)

## Estado

Fase 1 em andamento. Pronto: BL-01 (`kos init`), BL-02 (repositórios-fixture para testes), BL-03 (descoberta, `kos discover`), BL-04 (perfis de processamento e chave de fragmento), BL-05 (normalizador e parser Markdown com offsets exatos), BL-06 (JSON, YAML e texto), BL-07 (código como texto, provisório até o Tree-sitter), BL-22 (HTML, texto visível com posições) BL-08 (ingestão full: `kos ingest --full`) BL-09 (`kos rebuild`, reconstrução determinística a partir do Git) BL-10 (`kos search`, busca presa a uma revisão) BL-11 (`kos cite`, citação com releitura do blob e estado de verificação) BL-12 (auditoria de consultas e citações em `audit.sqlite`, `kos audit verify`) e BL-13 (`kos ask`, resposta extrativa com conflitos e abstenção).

## Uso

Requer Python ≥ 3.11 com SQLite compilado com FTS5. Dependências externas: `markdown-it-py` (Markdown com mapa de linhas, BL-05) e `PyYAML` (YAML com posição de cada nó, BL-06), as duas escolhidas pelo teste de offsets exatos; JSON, HTML e texto usam só a biblioteca padrão. Instale com `pip install -e .`.

```sh
PYTHONPATH=src python -m kos init            # cria ./.kos/index.sqlite e ./.kos/audit.sqlite
PYTHONPATH=src python -m kos init --json     # saída kos.init.v1
PYTHONPATH=src python -m kos discover ../mauricio-site --policy policies/mauricio-site.json
PYTHONPATH=src python -m kos ingest ../mauricio-site --full --policy policies/mauricio-site.json
PYTHONPATH=src python -m kos rebuild --repo mauricio-site=../mauricio-site --policy policies/mauricio-site.json
PYTHONPATH=src python -m kos search "piso de contraste da Camada 3" -k 5
PYTHONPATH=src python -m kos cite <fragment_key> --lines 121-121   # chave vinda do search --json
PYTHONPATH=src python -m kos ask "Qual é o piso de contraste da Camada 3?"   # saída 3 = abstenção
PYTHONPATH=src python -m kos audit verify <query_id> --repo mauricio-site=../mauricio-site
```

Políticas de elegibilidade ficam em `policies/` (a do corpus-alvo é `policies/mauricio-site.json`); sem `--policy`, vale a política empacotada em `src/kos/discovery/default_policy.json`.

Ou instale em modo editável (`pip install -e .`) e use `kos init`.

O diretório dos bancos é `--home`, ou `$KOS_HOME`, ou `./.kos`. `index.sqlite` pode ser apagado e reconstruído; `audit.sqlite` guarda a trilha de auditoria e não deve ser apagado.

## Testes

```sh
PYTHONPATH=src python -m unittest discover -s tests -t .
```

Para conferir os offsets de todos os parsers num corpus real (TC-PRS-01):

```sh
PYTHONPATH=src python scripts/dev/check_offsets.py ../mauricio-site --policy policies/mauricio-site.json
```

Os testes também conferem que o DDL em `src/kos/store/*.sql` é o mesmo da especificação e que o catálogo de erros é o de CTR-10.
