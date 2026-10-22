---
id: KOS-F0-TST
titulo: Plano de testes do MVP
status: rascunho para aprovação
data: 2026-10-21
---

# Plano de testes

## 1. Níveis

| Nível | O que cobre | Onde roda | Dados |
|---|---|---|---|
| Unidade | Funções puras: normalização, fingerprint, `fragment_key`, escape de consulta FTS, cálculo de métricas | Local e CI | Entradas literais |
| Contrato | TC-* de `03-contratos.md`: cada contrato isolado, com dublês só nas bordas (Git, relógio, LLM, rede) | Local e CI | Repositórios-fixture (§2) |
| Propriedade | Invariantes universais: determinismo, incremental ≡ full, toda citação tem estado, todo resultado está no manifesto | Local e CI | Sequências de commits geradas |
| Integração ponta a ponta | `kos init → ingest → search → cite → ask` sobre C0 | Local; CI se C0 puder ser clonado lá | C0 em `73570bb` |
| Benchmark | Golden set, métricas e recursos (`04-benchmark.md`) | Local, sob demanda e antes de mudar ADR | C0, depois C1 |

Benchmark não é teste de aprovação: não falha a CI por métrica baixa. O que falha a CI é o golden set deixar de se auto-verificar (TC-BEN-02) ou uma métrica de integridade quebrar (ex.: um `verified_exact` falso).

## 2. Fixtures

- **Construtor de repositórios-fixture**: script que cria repositórios Git temporários a partir de uma descrição declarativa (arquivos, commits, `git mv`, symlink, submódulo, ponteiro LFS, nome não UTF-8, CRLF). Autor, e-mail e datas fixos para que os commit OIDs sejam estáveis.
- **C0 fixado**: clone de `issei/mauricio-site` em `73570bbc9b99e2a1e44d6844b9375bc4aa16e357`. Só leitura. [ABERTO] Q-17: se o repositório é público (afeta usar C0 em CI de terceiros).
- **Dublê de LLM**: determinístico, programável por caso (responde com afirmações válidas, inventadas ou com referências a fragmentos não recuperados).
- **Dublê de transporte de rede**: falha o teste se qualquer conexão for aberta em modo padrão.

## 3. Testes transversais (não listados nos contratos)

| ID | Teste | Requisito |
|---|---|---|
| TC-CLI-01 | `kos <cmd> --json` valida contra o esquema `kos.<cmd>.v1` em todos os comandos | REQ-13 |
| TC-CLI-02 | Códigos de saída: 0 resposta, 3 abstenção, 4 parcial, 1 uso, 2 execução | REQ-13, CTR-10 |
| TC-CLI-03 | Saída humana de citação sempre contém o estado de verificação | REQ-08 |
| TC-CLI-04 | Todos os comandos funcionam sem rede (dublê de transporte) | RNF-03 |
| TC-MCP-01 | O servidor MCP lista exatamente `search`, `get_citation`, `ask_extractive` | REQ-14 |
| TC-MCP-02 | Pedido de caminho fora da política ou de leitura de arquivo arbitrário falha | REQ-14 |
| TC-MCP-03 | Toda chamada MCP gera `query_event` com `interface='mcp'` | REQ-12 |
| TC-SEC-01 | Com configuração padrão, nenhuma conexão de rede durante ingestão, busca, resposta e benchmark | RNF-01 |
| TC-ARQ-01 | Verificação estática: nenhuma dependência de biblioteca de embedding, vetor ou grafo no manifesto de dependências do núcleo; nenhuma coluna de vetor no esquema | RNF-06 |

## 4. Matriz contrato → testes

| Contrato | Testes |
|---|---|
| CTR-01 Descoberta | TC-DSC-01..07 |
| CTR-02 Parsing | TC-PRS-01..08 |
| CTR-03 Incremental | TC-INC-01..05 |
| CTR-04 Atualização/remoção | TC-UPD-01..05 |
| CTR-05 Rebuild | TC-REB-01..03 |
| CTR-06 Recuperação | TC-RET-01..06 |
| CTR-07 Citação | TC-CIT-01..06 |
| CTR-08 Resposta | TC-ANS-01..05 |
| CTR-09 Abstenção | TC-ABS-01..05 |
| CTR-10 Erros/auditoria | TC-AUD-01..05 |
| Benchmark | TC-BEN-01..04 |

## 5. Critério de pronto do caminho vertical mínimo

1. Todos os TC de CTR-01, 02 (formatos nativos), 03 (modo full), 05, 06, 07, 08 (extrativo), 09, 10 verdes.
2. TC-BEN-01..04 verdes; relatório B0 de C0 gerado e arquivado.
3. Zero `verified_exact` falsos no golden set.
4. TC-SEC-01 e TC-ARQ-01 verdes.
