---
id: KOS-REV-C0-01
titulo: Revisão independente do golden set C0, etapas A e B
data: 2026-10-22
leitor: Issei, árbitro humano (papel H)
plano: docs/fase-1/plano-revisao-multiagente.md
padrao_de_redacao: ABNT NBR ISO 24495-1 (linguagem simples) e ASD-STE100 adaptado ao PT-BR
---

# Revisão independente do golden set C0

## Para quem é este documento e o que ele pede

Este documento é para você, Issei, no papel de árbitro.
Ele traz o resultado das etapas A e B do plano de revisão.
Você precisa dar **3 respostas** (seção 5). Responda no chat com o código de cada opção, por exemplo "D1-A, D2-B".
Tempo estimado: 20 minutos.

## 1. Resumo

- **O golden set tinha erros.** O auditor (P3) provou defeito em 9 dos 14 casos. Em 5 casos o defeito muda o resultado medido.
- **9 dos 14 casos passam sem divergência.** O anotador cego (P2) dá o mesmo tipo de resposta que eu em 12 casos. Todas as 42 evidências que P2 citou conferem com o corpus. Nenhuma foi inventada.
- **Os números do B0 estão distorcidos.** Em 3 casos o golden set punia uma resposta correta. Exemplo: em GS-CODE-003 o sistema perde ponto se citar o segundo teste, que também é correto.
- **A classe "conflito" está fraca.** Nenhum dos 3 casos de conflito é um conflito real entre fontes. P2 e P3 explicam cada um de outra forma.
- **P1 escreveu 10 perguntas novas.** Elas não usam as palavras do corpus, porque P1 não leu o conteúdo dos arquivos.

## 2. Como foi feito

| Papel | Modelo | Recebeu | Entregou |
|---|---|---|---|
| P1 usuário real | Haiku | Só a lista de pastas e os títulos dos `.md` da raiz | `P1.yaml`, 10 perguntas |
| P2 anotador cego | Opus | As 14 perguntas, **sem** as respostas, e o corpus | `P2.yaml`, 14 respostas com evidência |
| P3 auditor | Sonnet | Os 14 casos completos e o corpus | `P3.yaml`, defeitos com prova |
| Script | — | As 3 saídas | `consolidado.json` |

- O corpus é uma cópia de `mauricio-site@73570bb`, sem o golden set.
- Os 3 agentes rodaram em paralelo. Nenhum viu a saída de outro.
- O script `scripts/review/consolidate.py` conferiu cada evidência contra o corpus. Um caso é **concordante** quando P2 e o golden set têm o mesmo tipo de resposta, a evidência de P2 cobre a esperada e P3 não tem defeito alto com prova.

Limites desta execução:

- O plano previa um modelo diferente da família do moderador para P2. O modelo previsto não estava disponível. P2 usou Opus, a mesma família do moderador. Por isso a amostra da seção 5.2 é importante.
- O isolamento dos agentes é por instrução. Os agentes tinham acesso técnico a outras pastas. Os relatos dos 3 agentes dizem que eles respeitaram o limite.

## 3. Números

| Medida | Valor |
|---|---|
| Casos concordantes | 9 de 14 |
| Mesmo tipo de resposta (P2 × golden) | 12 de 14 |
| Evidência de P2 cobre a esperada | 11 de 11 casos com evidência esperada |
| Evidências de P2 que não conferem com o corpus | 0 de 42 |
| Casos com defeito provado por P3 | 9 (alta: 3, média: 6) |
| Vazamento lexical pela regra do script (3 ou mais palavras) | 1 (GS-SPEC-001) |
| Vazamento lexical apontado por P3 | 3 (GS-SPEC-001, GS-CODE-002, GS-CODE-003) |

## 4. Os 5 casos divergentes

### GS-CONF-002: "Quantos KPIs cognitivos o Knowledge OS define?"

- **Golden set:** conflito. A página diz 18 e diz 22.
- **P2:** conflito, mas reconcilia: 18 cognitivos + 4 de FinOps = 22. P2 contou as 22 linhas da tabela.
- **P3:** **não** há conflito. A linha 690 já diz "18 KPIs cognitivos + FinOps". O golden set proíbe "um único número" e pune a resposta que reconcilia.
- **Leitura do moderador:** P2 e P3 concordam no fato (18 + 4 = 22). Eles divergem só no rótulo.

### GS-CONF-003: "Quantas páginas HTML existem em src/?"

- **Golden set:** abstenção. Proíbe afirmar "46 páginas".
- **P2:** conflito. Contou 46 arquivos em `src/*.html`. `AGENTS.md` diz 36 e `REPORT.md` diz 43.
- **P3:** a classe está errada. O caso proíbe o valor correto (46).
- **Leitura do moderador:** o caso quer testar que o sistema não transforma uma afirmação de documento em fato. O texto do caso não diz isso com clareza.

### GS-CONF-001: "O projeto usa Vite ou é sem build step?"

- **Golden set:** conflito.
- **P2:** sem conflito. O site usa Vite 6. O ADR-001 vale só para o subprojeto LifeOS.
- **P3:** pergunta ambígua. "O projeto" pode ser o site ou o LifeOS. Falta `AGENTS.md:11` ("Tech Stack: Vite 6").

### GS-CODE-002: "Onde é montado o bloco PF:START da home e qual função o grava no HTML?"

- **P3 (alta):** a resposta esperada está errada. `fill()` só troca o bloco em memória. Quem grava no disco é `writeFileSync`, na linha 608, fora de uma função.
- **P2:** chegou ao mesmo fato sozinho: pfBlock monta, `fill()` troca, `writeFileSync` grava.

### GS-CODE-003: "Qual teste verifica o contraste mínimo de 7:1 na Camada 3 da apresentação?"

- **P3 (alta):** existem 2 testes corretos. O golden set aceita só o de `tests/apresentacao.tokens.test.mjs:39`. O teste Playwright de `tests/apresentacao.spec.js:262` também verifica isto.
- **P2:** encontrou os 2 testes sozinho.

## 5. Decisões que preciso de você

### D1. Como corrigir os 5 casos divergentes

| Opção | O que acontece |
|---|---|
| **D1-A (recomendada)** | Eu aplico as correções abaixo no golden set. Os casos passam a aceitar as respostas corretas que P2 e P3 encontraram. |
| D1-B | Você corrige caso a caso, no chat. |
| D1-C | Eu removo os 5 casos e o golden set fica com 9. |

Correções da opção D1-A:

| Caso | Correção |
|---|---|
| GS-CONF-002 | Classe `spec_fact`. Resposta: "22 em 5 camadas, ou 18 sem FinOps". Aceita a reconciliação. |
| GS-CONF-003 | Classe `no_answer`. O sistema deve dizer que `AGENTS.md` afirma 36 e que o número não está verificado. Tiro "46" das respostas proibidas. |
| GS-CONF-001 | A pergunta passa a ser "O site usa Vite ou é sem build step?". Resposta: "usa Vite 6; o ADR-001 vale só para o LifeOS". Acrescento `AGENTS.md:11`. |
| GS-CODE-002 | Resposta: "`pfBlock` monta, `fill()` troca em memória, `writeFileSync` grava (linha 608)". |
| GS-CODE-003 | Aceita os 2 testes. Acrescento `tests/apresentacao.spec.js:262`. |

Efeito: a classe `conflict` cai de 3 para 0 casos reais verificados. Vou precisar de casos novos de conflito.

### D2. A amostra de 3 casos concordantes

O script sorteou 3 casos em que P2 concordou comigo (semente 20261022). Confira se a resposta de P2 está certa. Se você discordar de 1 ou mais, a concordância entre os agentes não vale como prova.

| Caso | Pergunta | Resposta cega de P2 |
|---|---|---|
| GS-ABS-001 | Qual é o RTO e o RPO do site em produção? | O corpus não define RTO nem RPO. P2 buscou RTO, RPO, "recovery time" e "recovery point" e achou 0 ocorrências. |
| GS-CODE-001 | O que acontece quando um hexadecimal é escrito em `src/apresentacao.html`? | O hook `PostToolUse` roda `scripts/guard-ap-tokens.mjs`. Ele sai com código 2 e devolve "[guard-ap] Hexadecimal proibido". O arquivo já foi gravado: o hook avisa, mas não desfaz. Um teste Playwright também reprova `#rrggbb` no body. |
| GS-SPEC-003 | Qual SLO de latência de recuperação a página do Knowledge OS declara? | P95 de retrieval < 800 ms. É um SLO "sugerido", uma meta, não uma medição. |

Responda **D2-ok** ou diga qual caso está errado.

### D3. As 10 perguntas de P1

| # | Classe | Quem pergunta | Pergunta |
|---|---|---|---|
| 1 | lexical | agente | Qual é o comando npm que atualiza as traduções em inglês e depois verifica se estão em dia? |
| 2 | spec_fact | dev novo | Qual é o nível de contraste de acessibilidade que o site precisa atingir? É WCAG AA ou AAA? |
| 3 | code | dono | Quando alguém digita um endereço antigo do site, qual função do CloudFront reescreve o caminho? |
| 4 | conflict | agente | Os documentos de acessibilidade concordam sobre quais páginas estão isentas das regras? |
| 5 | no_answer | dono | Quanto o Maurício paga por mês de hospedagem na AWS? |
| 6 | no_answer | dono | Quantas pessoas únicas visitaram o site no mês passado? |
| 7 | lexical | dev novo | Em que lugares do código o diretório lifeos é usado? |
| 8 | spec_fact | agente | Existe alguma decisão registrada que permita uma página fugir do tema escuro padrão do site? |
| 9 | code | dev novo | Como o gerador de SEO monta a meta description de cada página publicada? |
| 10 | spec_fact | dev novo | Antes de criar uma página nova no site, quais documentos eu preciso ler e em que ordem? |

| Opção | O que acontece |
|---|---|
| **D3-A (recomendada)** | Aceito as 10. Elas ainda não têm resposta: P2 anota às cegas e P3 audita, como nos 14 casos. Depois você confere só as divergências. |
| D3-B | Você escolhe quais aceitar, por número. |

Nota: as perguntas 2 e 10 podem ter mais de uma resposta correta. P3 vai avaliar isto.

## 6. Defeitos médios (sem decisão sua)

Estes defeitos não mudam o resultado do caso, mas punem uma citação correta.
Se você escolher D1-A, eu corrijo estes também.

| Caso | Correção |
|---|---|
| GS-SPEC-001 | A fonte do ADR-ap-001 aponta as linhas 25-28. O 7:1 está na linha 46. |
| GS-SPEC-003 | Acrescentar a linha 2133 ("Retrieval Latency P95 < 800ms") como evidência. |
| GS-CODE-001 | Acrescentar `ADR-ap-001` linha 74. Corrigir a fonte de `AGENTS.md` para a linha 125. |
| GS-ABS-002 | A página declara também a meta Recall@k > 0,85. Acrescentar como meta. |

## 7. Próximos passos depois das suas respostas

1. Aplico D1 e D3 no golden set. O resultado é o golden set v2.
2. Rodo `kos bench run` com o v2. O resultado é o relatório B1.
3. Etapa D do plano: P4 (metodólogo), P5 (dono do risco) e P6 (engenheiro de recuperação) analisam o B1.

## Arquivos

- `P1.yaml`, `P2.yaml`, `P3.yaml`: saídas dos agentes, sem edição.
- `consolidado.json`: saída do script.
