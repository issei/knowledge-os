---
id: KOS-F0-RSK
titulo: Riscos do MVP
status: rascunho para aprovação
data: 2026-10-21
---

# Riscos

Probabilidade e impacto são **minha estimativa** (Alta/Média/Baixa), não medição.

| ID | Risco | P | I | Mitigação | Gatilho de observação |
|---|---|---|---|---|---|
| RSK-01 | ~~Corpus-alvo desconhecido~~. Decidido em Q-01: o corpus é o `mauricio-site`. Resta o risco de o design ficar ajustado demais a um corpus pequeno | B | M | Q-01 antes da Fase 1; golden set separado por corpus; não tirar conclusões de C0 para C1 | Formatos ou volumes de C1 fora do previsto |
| RSK-02 | A página pública promete GraphRAG/vetores/agentes; expectativa diverge do MVP | A | M | ADR-kos-008 e DIV-01..05 registrados; Q-03 | Pedido de "busca semântica" antes de B0 |
| RSK-03 | Paráfrases não casam no FTS5; recall baixo em perguntas naturais | A | M | Medir em B0; análise de erros; campos `heading_path` e `ident_terms`; só depois considerar expansão de consulta | Recall@10 de B0 baixo com falhas de vocabulário |
| RSK-04 | Parser sem posições confiáveis quebra a citação exata | M | A | ADR-kos-003 exige offsets; TC-PRS-01 em 100% dos fragmentos | Qualquer falha em TC-PRS-01 |
| RSK-05 | Normalização diferente entre indexação e verificação gera `unverified` em massa ou, pior, `verified_exact` falso | M | A | Uma única função de normalização versionada, usada nos dois lados; teste de falso positivo | Taxa de rótulo correto < 100% |
| RSK-06 | Limiar de abstenção mal calibrado: responde sem suporte ou se abstém demais | A | A | Calibração com curva e regra de custo aprovada (Q-15); reportar as duas taxas juntas | Golden set pequeno demais para curva estável |
| RSK-07 | Golden set pequeno e rotulado por uma só pessoa (eu) | A | M | Segundo anotador; crescimento por classe (Q-14) | Mudança de conclusão com 1 caso a mais |
| RSK-08 | Conteúdo privado enviado a terceiros via LLM remoto ou cliente MCP | M | A | LLM desligado por padrão, opt-in por repositório; MCP só leitura e local; TC-SEC-01 | Configuração de provedor remoto |
| RSK-09 | Injeção de instruções em documentos recuperados afeta o LLM ou o agente cliente | M | M | Conteúdo tratado como dado; validador de referências; marcação de origem no MCP | Fragmento com instruções imperativas no golden set (adicionar caso) |
| RSK-10 | Reescrita de histórico (force-push) apaga commits retidos; citações antigas viram `unverified` | M | M | Rebuild tolera ausência; auditoria guarda trecho e hash | `E_COMMIT_NOT_FOUND` no rebuild |
| RSK-11 | Arquivos gerados (ex.: `src/en/**`) competem com a fonte e geram citações duplicadas ou em tradução automática | A (em C0) | M | Classificação `generated` na política; filtro padrão; CTR-07 inv. 6 | Citações para `*/en/*` no benchmark |
| RSK-12 | Bindings Python do Tree-sitter e das gramáticas mudam de API entre versões (linguagem decidida em Q-02: Python) | M | M | Fixar versões no perfil; TC-PRS-05 | Quebra ao atualizar gramática |
| RSK-13 | Implementar dentro do `mauricio-site` dispararia deploy de produção a cada merge em `main` e sujeitaria o código às regras do site (i18n, gate de páginas) | M | A | Recomendação: repositório próprio (Q-19) | Proposta de PR no `mauricio-site` com código |
| RSK-14 | Uso do TGI de 2004 como corpus de PDF sem consentimento dos coautores | B | A | Não usar sem decisão de Issei (Q-13) | — |
