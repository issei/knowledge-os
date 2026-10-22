# CI/CD

Pedido de Issei (2026-10-22): ao abrir um PR, rodar em paralelo só os testes necessários, entregar quando houver necessidade e, se tudo passar, fazer o merge automático na `main`. Mudanças só de documentação também entram automaticamente.

## Fluxo

```text
PR aberto/atualizado
  └─ changes ── classifica os arquivos (scripts/ci/classify_changes.py)
       ├─ docs   ── links relativos dos .md (scripts/ci/check_docs.py)      [se mudou documento]
       ├─ build  ── compileall + wheel, confere o DDL dentro do wheel       [se mudou sistema]
       └─ tests  ── matriz py3.11/3.12/3.13 × unit/contract (6 jobs)        [se mudou sistema]
  └─ ci-ok ── passa se todo job necessário passou ou foi pulado
       (automerge e release usam `!cancelled()`: sem isso o GitHub os pula quando build e tests foram pulados)
  └─ automerge ── squash merge na main (só PR do próprio repositório, fora de rascunho)
  └─ release ── só se a mudança tocou o sistema: chama release.yml
```

Os jobs `docs`, `build` e `tests` rodam em paralelo. Um push novo no mesmo PR cancela a execução anterior.

## O que é "sistema" e o que é "só documentação"

Regra única, em `scripts/ci/classify_changes.py` e coberta por `tests/unit/test_ci_scripts.py`:

| Conta como sistema (roda build e testes) | Conta como documentação (só verificação de links) |
|---|---|
| `src/**`, `tests/**`, `scripts/**`, `.github/**`, `pyproject.toml` | demais `*.md` e `docs/**` |
| `docs/fase-0/02-modelo-de-dados.md` e `03-contratos.md`, porque os testes conferem que o DDL e o catálogo de erros do código batem com eles | |
| qualquer arquivo fora das duas listas (por segurança) | |

Um PR só de documentação passa por `docs` e `ci-ok` e é mesclado sem rodar a suíte.

## Entrega (release.yml)

"Quando houver necessidade" significa: a versão em `pyproject.toml` ainda não tem a tag `v<versão>`. Nesse caso o workflow roda a suíte completa, gera wheel e sdist e cria uma GitHub Release com os arquivos. Versões com letras (`0.1.0.dev0`, `1.0.0rc1`) saem como pré-release. Sem mudança de versão, o release termina sem fazer nada.

Para entregar uma versão nova, basta subir a versão no `pyproject.toml` (e em `src/kos/__init__.py`) dentro do PR.

O release roda em dois caminhos:
- chamado pela CI logo depois do merge automático, porque um merge feito pelo `GITHUB_TOKEN` não dispara novos workflows;
- em push na `main` que toque `src/**` ou `pyproject.toml`, para merges feitos pelo botão.

A verificação de tag torna as duas rotas idempotentes.

Não há deploy para servidor: o produto é uma CLI local (ADR-kos-005) e a entrega é o pacote na Release.

## Salvaguardas

- O merge automático usa `--match-head-commit`: se alguém empurrar um commit depois do início da execução, o merge é recusado e a nova execução decide.
- PRs de fork e PRs em rascunho nunca são mesclados automaticamente.
- Permissões mínimas: `contents: read` por padrão; escrita só nos jobs `automerge` e `release`.

## Configuração no GitHub (opcional, recomendada)

- Proteção da `main` com o check obrigatório **CI ok**. Assim, merges pelo botão também exigem a CI verde. Se a proteção exigir aprovação de revisor, o merge automático vai falhar até alguém aprovar.
