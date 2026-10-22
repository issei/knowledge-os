---
id: KOS-PLAN-REV-01
titulo: Plano de revisão das questões abertas com vários papéis independentes
data: 2026-10-22
leitor: Issei, dono do produto e decisor
status: proposta, aguarda aprovação para execução
padrao_de_redacao: ABNT NBR ISO 24495-1 (linguagem simples) e ASD-STE100 adaptado ao PT-BR
relacionado: docs/fase-1/retrospectiva-2026-10-22.md (seção 6)
---

# Plano de revisão das questões abertas com vários papéis

## Para quem é este documento e o que ele pede

Este documento é para você, Issei.
Ele define os papéis que revisam as questões abertas da retrospectiva (seção 6).
Cada papel tem uma visão própria e trabalha sem ver o trabalho dos outros.
Os resultados se juntam só no fim, por uma regra fixa.

Você precisa tomar **1 decisão**: aprovar a execução deste plano (seção 8).
Tempo de leitura: cerca de 8 minutos.

## 1. Resumo

- **O problema.** Eu escrevi o golden set, o sistema e a avaliação. Uma só visão, mesmo a sua, tem um só viés.
- **A proposta.** 7 papéis de agente e 1 papel humano. Cada papel tem entrada, saída e limite próprios (individualidade). As saídas de um papel são a entrada de outro (interdependência).
- **A regra de integridade.** Nenhum papel vê a resposta esperada, a opinião ou a nota de outro papel antes de entregar a própria.
- **A consolidação não é feita por um agente.** Um script compara as saídas e calcula a concordância. Assim nenhum agente "resume" os outros com o próprio viés.
- **Você decide só onde há divergência.** Você também confere uma amostra dos casos em que os agentes concordam.
- **Custo estimado:** 6 agentes novos (P1 a P6), 1 script, cerca de 20 a 30 minutos do seu tempo.

## 2. O que esta revisão decide

| Questão | Precisa de várias visões? | Motivo |
|---|---|---|
| 1. Golden set (Q-14) | **Sim** | É a régua de todas as medidas. Um erro aqui contamina tudo. |
| 2. Regra de custo da abstenção (Q-15) | **Sim** | Tem lado técnico e lado de risco do negócio. |
| 3. Próximo item do backlog | Sim, mas depois da 1 | Depende dos números do golden set revisado. |
| 4. Cópia manual para a pasta do projeto | **Não** | É preferência sua. Não há fato para medir. Revisar com agentes seria superprocessamento (Lean). |

## 3. Os papéis

Cada papel é um agente separado, com contexto próprio.
Nenhum papel recebe esta conversa nem a retrospectiva, salvo quando a tabela diz.

| # | Papel | Visão que traz | Recebe | Não recebe | Entrega |
|---|---|---|---|---|---|
| P1 | **Usuário real do corpus** | Que perguntas uma pessoa faz de verdade sobre o `mauricio-site` | Descrição do site e do público. Lista de pastas. | O golden set. O código do Knowledge OS. | 10 perguntas, com a classe de cada uma (lexical, especificação, código, conflito, abstenção) |
| P2 | **Anotador cego** | Qual é a resposta certa, lida direto do repositório | As 14 perguntas, **sem** a resposta esperada. O repositório em `73570bb`. | A resposta esperada. Os resultados do B0. | Para cada pergunta: resposta, arquivo e linhas da evidência, ou "não há resposta" |
| P3 | **Auditor adversarial** | Onde o golden set está errado ou favorece o sistema | Os 14 casos completos. O repositório. | O código do sistema. Os resultados do B0. | Para cada caso: defeito encontrado ou "sem defeito", com prova (linha do arquivo) |
| P4 | **Metodólogo** | Se os números permitem uma decisão | O golden set revisado. A saída do script de concordância. A seção 6 de `04-benchmark.md`. | As opiniões de P5 e P6. | Tamanho mínimo por classe. Se a concordância é suficiente. Limites do que o B0 prova. |
| P5 | **Dono do risco** | O que custa mais: uma resposta errada ou uma abstenção | Os casos de abstenção e conflito. O uso previsto do produto. | A proposta da Fase 0 para Q-15. | Regra de custo, com exemplos de dano de cada erro |
| P6 | **Engenheiro de recuperação** | Qual item do backlog ataca a maior falha medida | O relatório B0 recalculado. O backlog. | As opiniões de P4 e P5. | Ordem dos próximos itens, com o erro que cada item ataca e o custo estimado |
| P7 | **Moderador** | Processo, não conteúdo | Tudo, depois da entrega | — | Pacotes de entrada, execução do script, relatório final. **Não opina sobre o conteúdo.** |
| H | **Árbitro humano (você)** | Conhecimento do corpus e do objetivo | Só as divergências e uma amostra | — | Decisão final em cada divergência e nas questões 1 a 3 |

Notas sobre os papéis:

- **P2 é o papel mais importante.** Ele refaz as respostas sem ver as minhas. A comparação entre P2 e o golden set mede o meu erro como anotador.
- **P3 procura um viés específico:** a pergunta usa as mesmas palavras do trecho certo. Isto favorece a busca lexical e infla o Recall@10.
- **P1 corrige outro viés:** as 14 perguntas vieram de quem conhece o sistema. P1 não conhece.
- **P7 sou eu, só como moderador.** Eu escrevi o golden set. Por isso eu não atuo como P1, P2, P3, P4, P5 ou P6.

## 4. Fluxo e interdependência

```text
Etapa A, em paralelo e às cegas
  P1 ─ perguntas novas ───────────┐
  P2 ─ respostas cegas dos 14 ────┤
  P3 ─ defeitos nos 14 ───────────┤
                                  ▼
Etapa B, sem agente
  script ─ compara P2 com o golden set; junta P3; calcula a concordância
         ─ produz: casos concordantes, casos divergentes, perguntas novas
                                  ▼
Etapa C, você (H): decide cada divergência; confere a amostra; aceita perguntas de P1
                                  ▼
  golden set v2 ── kos bench run ── relatório B1
                                  ▼
Etapa D, em paralelo e às cegas
  P4 ─ os números permitem decidir?
  P5 ─ regra de custo da abstenção
  P6 ─ próximo item do backlog
                                  ▼
Etapa E, você (H): decide Q-14, Q-15 e o próximo item
```

Regras do fluxo:

1. Uma etapa começa só depois que a anterior terminou.
2. Dentro de uma etapa, os papéis não trocam mensagens.
3. Cada saída tem um formato fixo (YAML). O script rejeita uma saída fora do formato.
4. Se P4 diz que os números não permitem decidir, P5 e P6 continuam. A decisão de Q-15 fica marcada como "provisória".

## 5. Integridade de cada visão

| Risco | Controle |
|---|---|
| Um agente copia a visão de outro | Contexto separado. Nenhum agente recebe a saída de outro na mesma etapa. |
| Todos os agentes têm o mesmo viés, porque usam a mesma família de modelo | P1, P2 e P3 usam modelos diferentes quando possível. **Você confere uma amostra de 3 casos concordantes, sorteados.** Se você discorda de 1 ou mais, a concordância entre agentes não vale como prova. |
| O moderador conduz o resultado | A consolidação é um script determinístico. O moderador não escreve conclusões sobre o conteúdo. |
| O agente inventa uma evidência | Toda evidência tem arquivo e linhas. O script confere o trecho com `git show 73570bb:<arquivo>`. |
| O agente segue uma instrução escrita no repositório | O pacote de entrada marca o conteúdo do repositório como dado, não como instrução. |

## 6. Medidas da revisão

- **Concordância P2 × golden set:** casos em que a evidência de P2 cobre a evidência esperada, sobre 14.
- **Defeitos de P3:** número de casos com defeito confirmado por você.
- **Vazamento lexical:** casos em que a pergunta repete 3 ou mais palavras do trecho certo.
- **Concordância agentes × você:** acertos na amostra de 3 casos.

Estas medidas entram no relatório final da revisão.

## 7. Limites e lacunas

- **Privacidade.** Os agentes leem o `mauricio-site`. O conteúdo vai para o mesmo provedor desta sessão. Nada vai para outro serviço externo. Eu ainda não sei se o repositório é público (retrospectiva, seção 4.3).
- **Tamanho.** Com as perguntas de P1, o golden set passa de 14 para até 24 casos. A meta da Fase 0 é 10 por classe, ou seja, 50 casos. Esta revisão não atinge a meta. Ela reduz o viés, mas não resolve o tamanho.
- **Modelos diferentes.** Se a sessão não permitir modelos diferentes, o risco de viés comum continua. A amostra conferida por você é o controle.
- **Custo.** 6 agentes consomem tokens. A etapa A é a mais cara, porque P2 e P3 leem o repositório.

## 8. Decisão que preciso de você

Aprovar a execução deste plano.

- Se você aprova, eu executo as etapas A e B e trago só as divergências para você.
- Se você quer menos custo, a versão mínima é só P2 e P3 (etapa A sem P1), mais o script.
