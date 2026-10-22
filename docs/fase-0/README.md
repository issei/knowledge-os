---
id: KOS-F0
titulo: Knowledge OS Enterprise — Fase 0 (especificação executável do MVP)
status: rascunho para aprovação de Issei
data: 2026-10-21
corpus_inspecionado: issei/mauricio-site @ 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
---

# Knowledge OS Enterprise — Fase 0

Especificação verificável do MVP, no formato Spec-Driven Development. Nenhuma funcionalidade foi implementada, nenhum arquivo existente foi alterado, nada foi instalado e nenhum conteúdo foi enviado a serviço externo.

## Documentos

| Arquivo | Fase | Conteúdo |
|---|---|---|
| [00-inventario.md](00-inventario.md) | 0A | Inventário com caminhos e linhas, estado da implementação (zero), divergências DIV-01..09 |
| [01-requisitos.md](01-requisitos.md) | — | REQ-01..15, RNF-01..06 |
| [02-modelo-de-dados.md](02-modelo-de-dados.md) | 0B | Identidades lógica/versão/fragmento, localizadores, DDL de `index.sqlite` e `audit.sqlite`, estratégia por tabela |
| [03-contratos.md](03-contratos.md) | 0C | CTR-01..10 com entradas, saídas, invariantes, falhas e testes |
| [04-benchmark.md](04-benchmark.md) | 0D | Golden set de 14 casos sobre C0, lacunas, métricas separadas, linha de base e calibração |
| [05-adrs.md](05-adrs.md) | 0E | ADR-kos-001..008 (aceitos em 2026-10-22) |
| [06-plano-de-testes.md](06-plano-de-testes.md) | — | Níveis, fixtures, testes transversais, critério de pronto |
| [07-riscos.md](07-riscos.md) | — | RSK-01..14 |
| [08-backlog.md](08-backlog.md) | 0F | BL-00..23 por dependência; BL-01..14 + BL-22 = caminho vertical mínimo |
| [09-consistencia.md](09-consistencia.md) | — | Matriz de rastreabilidade, verificações feitas, questões abertas Q-01..19 |

## Resumo das decisões propostas

1. **Git é a fonte de verdade**; `index.sqlite` é descartável e reconstruível de forma determinística; a auditoria fica em `audit.sqlite`, que o rebuild não toca (ADR-kos-001).
2. **Três identidades**: artefato lógico (repo + caminho em bytes), versão (blob Git) e fragmento (hash de blob + perfil + localizador). A presença por commit fica num manifesto, sem duplicar conteúdo.
3. **SQLite/FTS5** com `bm25()`, acentos removidos na tokenização e identificadores de código divididos; toda busca é presa a uma revisão (ADR-kos-002).
4. **Parsers com posições no original**: nativos para MD/YAML/JSON/texto, Tree-sitter para código, Docling só em perfil opcional com localizador de página (ADR-kos-003).
5. **Citação com estado de verificação obrigatório** (`verified_exact`, `verified_normalized`, `derived`, `unverified`), conferida relendo o blob no Git (ADR-kos-004).
6. **CLI `kos`** com saída JSON versionada; **MCP local só leitura** com 3 ferramentas, depois do caminho vertical (ADR-kos-005, 006).
7. **Resposta extrativa por padrão**; LLM opcional, desligado, só vê fragmentos recuperados, e afirmações sem suporte são removidas (ADR-kos-007).
8. **Sem embeddings/grafos** até haver linha de base B0 e análise de erros; divergência com a página pública registrada (ADR-kos-008).
9. **Nenhuma meta numérica** fixada: a página publica "Recall@10 > 0.75" e "P95 < 800 ms" sem medição; ficam como hipóteses contra B0.

## Fatos, inferências e lacunas principais

- **Fato:** não há implementação do Knowledge OS em nenhum local acessível; só a página `knowledge-os-presentation` do site.
- **Fato:** a página tem contradição interna (18 KPIs em 4 camadas vs. 22 KPIs em 5 camadas) e `AGENTS.md` cita 36 páginas onde há 46. Ambos viraram casos do golden set.
- **Decidido (2026-10-21):** corpus-alvo `mauricio-site` (Q-01), Python (Q-02), HTML no MVP (Q-05), repositório `issei/knowledge-os` (Q-19). Ver `09-consistencia.md` §4.
- **Lacuna:** corpus corporativo-alvo, formatos PDF/DOCX reais, perguntas de usuários reais.

## Antes da Fase 1

ADRs aceitos em 2026-10-22 (BL-00 concluído). As questões Q-01, Q-02, Q-05 e Q-19 já foram respondidas.
