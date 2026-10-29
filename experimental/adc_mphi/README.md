# ADC × MPHI — Conector experimental v0.1 (somente leitura)

Objetivo: ler as previsões congeladas (`forecast_ledger.json` e `hydrologic_ledger.json`) e as medições publicadas (`latest.json`) do MPHI e produzir diariamente um relatório de aprendizagem. O código não altera os dados, o site, os scripts de coleta, os modelos ou a baseline do MPHI.

## Execução

`python -m experimental.adc_mphi.runner --repo-root . --output-dir adc_mphi_report`

O workflow `.github/workflows/adc-mphi-learning.yml` executa testes e emite `report.json` e `report.md` diariamente às 15h30 de Manaus (19h30 UTC). Os resultados ficam como **artefatos do GitHub Actions por 90 dias**; também é possível iniciar `workflow_dispatch`. Atrasos/omissões de agendamento e indisponibilidade da fonte continuam possíveis.

A comparação usa apenas as previsões centrais *registradas* e cota observada na data-alvo, sem interpolar ou aproximar. O controle ingênuo de persistência é gerado a partir da cota declarada na emissão da previsão v1.0. Comparações entre versões usam exclusivamente pares com a mesma data de emissão, data-alvo e horizonte. A saída lista erros MAE, viés (observado − previsto), RMSE e amostras N. Hipóteses de aprendizagem são apenas propostas, nunca ajustes automáticos.

**Limitação central:** este adaptador emite análises em snapshots; ele **não grava no ledger SQLite append-only do ADC v0.1** nem autentica a data histórica das previsões. A fonte declara seu histórico; cada execução fixa hashes SHA-256 dos três arquivos de entrada. O piloto ADC já iniciou separadamente, em 29/10/2026, com 12 previsões prospectivas do MPHI e do controle de persistência. A futura conexão aos eventos `OUTCOME_OBSERVED` precisará de um mecanismo de custódia de ledger e confirmação de evidências por autoridade responsável. Não tratar relatórios como promoção no Gauntlet.

**Governança:** nenhum acesso de escrita no workflow (`permissions: contents: read`); não há `git push`, notificação automática externa, credenciais adicionais, alteração de página, ou promoção de versões. Baseline operacional preservada. Para evolução, abrir mudança e validar separadamente.