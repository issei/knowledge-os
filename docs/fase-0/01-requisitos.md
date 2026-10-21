---
id: KOS-F0-REQ
titulo: Requisitos do MVP do Knowledge OS Enterprise
status: rascunho para aprovação
data: 2026-10-21
---

# Requisitos do MVP

Fonte: pedido de Issei de 2026-10-21 (arquitetura provisória aprovada) e inventário `00-inventario.md`.
Cada requisito tem ID estável; `09-consistencia.md` liga cada um a ADRs, contratos, testes e itens de backlog.

## Objetivo do MVP

Responder perguntas técnicas sobre um corpus versionado em Git (documentação, especificações, ADRs, código e testes) com **evidências rastreáveis e verificáveis**, ou se abster quando não houver evidência suficiente. O caminho vertical mínimo é: ingestão → indexação → recuperação → citação verificável → avaliação.

## Fora do escopo do MVP

Embeddings, bancos vetoriais, bancos de grafos, GraphRAG, orquestração multiagente, escrita em repositório, interface web, multiusuário com controle de acesso por documento (ver Q-08), formatos binários sem parser aprovado.

## Requisitos funcionais

| ID | Requisito | Verificação |
|---|---|---|
| REQ-01 | O repositório Git e os artefatos originais são a fonte de verdade. Todo dado do índice é derivado e pode ser apagado e reconstruído a partir de (repositório, revisão, política, perfis de processamento). | TC-REB-01..03 |
| REQ-02 | A descoberta de artefatos elegíveis é determinística para uma revisão e uma política de elegibilidade versionada. Lê o conteúdo da árvore do commit, nunca da cópia de trabalho. | TC-DSC-01..07 |
| REQ-03 | Markdown, YAML, JSON e texto estruturado usam parsers nativos. Código usa Tree-sitter para sintaxe e símbolos. Docling só para formatos documentais complexos, atrás de um perfil opcional. | TC-PRS-01..08 |
| REQ-04 | A ingestão é incremental: entre duas revisões, só artefatos com blob alterado são reprocessados; artefatos com blob igual reaproveitam o resultado. | TC-INC-01..05 |
| REQ-05 | Remoções e renomeações na revisão-alvo deixam de aparecer nas buscas daquela revisão, sem apagar o histórico de revisões anteriores retidas. | TC-UPD-01..05 |
| REQ-06 | A busca textual usa SQLite FTS5 com filtros por repositório, revisão, caminho, tipo de artefato e linguagem. | TC-RET-01..06 |
| REQ-07 | Toda evidência retornada tem localizador: repositório, caminho, commit, e quando aplicável intervalo de linhas, página, ponteiro estrutural ou símbolo, mais o trecho e o hash do conteúdo. | TC-CIT-01..06 |
| REQ-08 | Uma localização nunca é apresentada como verificada se não foi conferida contra o conteúdo do blob. Cada citação carrega um estado de verificação explícito. | TC-CIT-03..05 |
| REQ-09 | Respostas fundamentadas ligam cada afirmação a pelo menos uma citação verificada. Existe um modo extrativo sem LLM. | TC-ANS-01..05 |
| REQ-10 | O sistema se abstém, com motivo codificado, quando a evidência é insuficiente, e diz o que procurou. | TC-ABS-01..05 |
| REQ-11 | Fontes conflitantes são relatadas lado a lado com suas citações; o sistema não escolhe um vencedor sem regra explícita. | TC-ANS-04, GS-CONF-* |
| REQ-12 | Toda execução de ingestão, erro de processamento e consulta fica registrada para auditoria, em armazenamento que sobrevive à reconstrução do índice. | TC-AUD-01..05 |
| REQ-13 | A CLI é a interface primária, com saída humana e saída JSON de esquema versionado, e códigos de saída estáveis. | TC-CLI-01..04 |
| REQ-14 | A integração MCP é somente leitura e expõe apenas recuperação e citação, sem ingestão nem escrita. Planejada; fora do caminho vertical mínimo. | TC-MCP-01..03 |
| REQ-15 | Existe um benchmark próprio, versionado e reprodutível, que mede recuperação e resposta separadamente. | TC-BEN-01..04 |

## Requisitos não funcionais

| ID | Requisito | Verificação |
|---|---|---|
| RNF-01 | Nenhum conteúdo do corpus é enviado a serviço externo sem configuração explícita de opt-in. O adaptador de LLM vem desligado. | TC-SEC-01, TC-ANS-05 |
| RNF-02 | Reconstrução determinística: duas reconstruções com as mesmas entradas produzem as mesmas chaves de fragmento e o mesmo conteúdo indexado. | TC-REB-02 |
| RNF-03 | Funciona offline em uma máquina de desenvolvedor, sem serviço residente. | TC-CLI-04 |
| RNF-04 | Latência, memória e tamanho do índice são medidos e reportados; metas numéricas só depois da linha de base (`04-benchmark.md` §6). | TC-BEN-04 |
| RNF-05 | Caminhos Git são tratados como bytes; nomes não ASCII e não UTF-8 não quebram a ingestão. | TC-DSC-04 |
| RNF-06 | Nenhuma dependência de embeddings, vetores, grafos ou orquestração multiagente no núcleo. | TC-ARQ-01 |
