# MPHI — Modelo Preditivo Hidrológico Uiara

Painel operacional para acompanhamento e projeção do nível do Rio Negro em Manaus, com foco em comportamento do rio, tendência, velocidade de vazante/enchente, aceleração, drawdown, posição sazonal, persistência e projeções de 7, 15 e 30 dias.

## Publicação

O site é publicado pelo GitHub Pages a partir da pasta `docs/` e atualizado por GitHub Actions.

## Atualização diária

O workflow `.github/workflows/update-and-deploy-mphi.yml` agenda a primeira coleta para **08:00 America/Manaus (12:00 UTC)**, todos os dias. Reconsulta nos minutos 07, 22, 37 e 52 de cada hora entre 08:07 e 23:52 de Manaus. A coleta independe de visitas ao site.

**Limite da infraestrutura:** o GitHub Actions pode atrasar ou descartar execuções agendadas. Esta configuração oferece tentativas recorrentes, não uma garantia de pontualidade às 08:00. A atualização também depende da disponibilidade do Porto e da publicação no Pages. O Porto expõe a data da medição, mas não a hora exata em que a publicou. Não se atribui uma hora fictícia à fonte.

O script `scripts/sync_mphi.py`:

1. consulta o Porto com tentativas adicionais para falhas temporárias;
2. recupera medições do mês atual e anterior, inclusive na virada do mês;
3. rejeita dados futuros, regressões de data, tabelas conflitantes e saltos anômalos;
4. recalcula e preserva uma previsão apenas quando os dados mudam;
5. mantém previsões anteriores intactas e valida datas-alvo com observação disponível;
6. registra a consulta em `docs/data/status.json`, inclusive quando não há medição nova;
7. publica os dados e verifica os quatro arquivos públicos.

`latest.json.meta.updated_at` é o instante real da alteração dos dados. `status.json.checked_at` é o instante da consulta ao Porto. Acesso, recarga, dia sem leitura e falha de fonte não mudam o horário da última atualização válida. Em caso de falha, o painel preserva os dados e exibe a indisponibilidade; a execução fica marcada como falha após a publicação desse estado.

O navegador consulta a publicação a cada minuto enquanto a página estiver visível e ao retornar à aba. Isso apenas carrega o estado compartilhado. Não executa coleta nem gera horário de atualização. Valores manuais locais antigos não substituem o dado oficial.

## Interface

Panorama com medição e pontuação; gráfico com períodos de 30/60 dias e série completa; cenários de 7/15/30 dias; confiabilidade e critérios expansíveis. Verde profundo, marfim e cobre; layout responsivo, foco por teclado e preferência de movimento reduzido. As médias são identificadas como últimas leituras disponíveis, não velocidade de corrente.

## Verificação

`python -m unittest discover -s tests -v` verifica os contratos da coleta e preservação dos dados. `node --check docs/app.js` verifica a sintaxe da interface.

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

- `docs/data/status.json` — estado e horário real da consulta à fonte;
- `docs/data/latest.json` — estado atual do MPHI;
- `docs/data/forecast_ledger.json` — previsões congeladas;
- `docs/data/validation.json` — resultados de backtesting prospectivo.

## Fonte operacional

Porto de Manaus. O histórico de referência do projeto utiliza Manaus 14990000 — ANA/SGB.
