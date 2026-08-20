# MPHI — Modelo Preditivo Hidrológico Uiara

Painel operacional para acompanhamento e projeção do nível do Rio Negro em Manaus, com foco em comportamento do rio, tendência, velocidade de vazante/enchente, aceleração, drawdown, posição sazonal, persistência e projeções de 7, 15 e 30 dias.

## Publicação

O site é publicado pelo GitHub Pages a partir da pasta `docs/` e atualizado por GitHub Actions.

## Atualização diária

O workflow `.github/workflows/update-and-deploy-mphi.yml` executa duas janelas diárias, 07:50 e 08:20 no horário de Manaus. A segunda funciona como contingência.

O script `scripts/update_mphi.py`:

1. consulta a página do Porto de Manaus;
2. atualiza a série operacional;
3. recalcula o MPHI;
4. congela uma previsão diária no ledger;
5. valida automaticamente previsões vencidas de 7, 15 e 30 dias;
6. grava os indicadores de validação;
7. republica o painel.

## Validação contínua

`docs/data/forecast_ledger.json` é o registro append-only das previsões. Uma previsão já emitida não é recalculada com informação futura.

`docs/data/validation.json` compara cada projeção central com a cota observada na data-alvo e calcula, por horizonte e versão do modelo:

- número de amostras maduras;
- MAE;
- viés;
- RMSE;
- cobertura do envelope suave–estresse.

Lead time, falsos alertas e alertas perdidos permanecem em coleta até existir critério observacional independente e janela suficiente para avaliação sem circularidade.

## Dados principais

- `docs/data/latest.json` — estado atual do MPHI;
- `docs/data/forecast_ledger.json` — previsões congeladas;
- `docs/data/validation.json` — resultados de backtesting prospectivo.

## Fonte operacional

Porto de Manaus. O histórico de referência do projeto utiliza Manaus 14990000 — ANA/SGB.
