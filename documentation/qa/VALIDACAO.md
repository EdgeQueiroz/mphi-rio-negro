# Validação da entrega meteorológica e visual

Referência: implementação `17c93d07605bf27ad2aa8cd00136562b9fc23846`, publicada em 28/09/2026 UTC (27/09 em Manaus).

## Confirmado

- 20 testes existentes do MPHI aprovados.
- 14 testes da integração meteorológica aprovados: sucesso com fixtures de contrato, timeout/falha total e parcial, ausência/remoção de token, cidade errada, contrato inválido, valores nulos/zero, horários, regressões, append-only, idempotência e isolamento.
- 6 testes JavaScript aprovados: renderização/escape, cache, indisponibilidade, ausência de credencial, contrato inválido, observação antiga e retenção após falha (alguns casos compartilhados nos mesmos testes).
- `node --check` nos dois scripts frontend e `git diff --check` aprovados.
- Atualização hidrológica real no GitHub sem credencial Climatempo concluída. Também se testou nova medição em diretório temporário com falha meteorológica.
- Workflow meteorológico: https://github.com/EdgeQueiroz/mphi-rio-negro/actions/runs/36366191447 — sucesso, incluindo prefixo meteorológico imutável, ausência de alterações hidrológicas, deploy e comparação dos JSON públicos.
- Workflow hidrológico: https://github.com/EdgeQueiroz/mphi-rio-negro/actions/runs/36366191432 — sucesso, incluindo coleta, proteção dos ledgers e confirmação pública.
- Comparação adicional via HTTPS: `latest.json`, `forecast_ledger.json`, `validation.json` e `hydrologic_ledger.json` públicos iguais à referência inicial. Todas as 34 previsões existentes (27 oficiais + 7 shadow) e 7 previsões hidrológicas preservadas.
- Arquivos dos motores e workflow hidrológico existentes não foram alterados. SHA-256 dos JSON iniciais em `hydrological-baseline-sha256.json`; `status.json` pode avançar normalmente a cada consulta.
- Site público carregado e inspecionado em desktop (viewport 1363 × 936): cota 19,78 m, score 9, classificação ALTO, meteorologia aguardando ativação. Sem rolagem horizontal.
- Botão 30 dias, navegação por seção e detalhes meteorológicos funcionam. Tabela pública confere com os dados: MAE 18,1 / 52,1 / 169,0 cm para 7/15/30 dias.
- Console sem erro do código MPHI. O navegador de inspeção emitiu erro de uma extensão interna, com origem `chrome-extension://`, sem vínculo com os scripts do site.
- GitHub Pages anuncia cache CDN `max-age=600`; consultas JSON usam parâmetro único e `cache: no-store`. Assets alterados recebem versão no HTML. O teste de cache do renderer valida essa configuração.
- Nenhuma credencial foi colocada no frontend. Chamadas autenticadas só existem no runner e apontam ao domínio oficial via HTTPS.

## Pendências e limites explícitos

- **Climatempo ao vivo:** o runner retornou `not_configured`. Falta o secret `CLIMATEMPO_TOKEN`. O sucesso da API foi testado com fixtures sintéticas baseadas na documentação, não com observações reais de Manaus. Nenhuma fixture foi publicada nos JSON do site.
- **iPhone:** CSS responsivo implementado, porém a inspeção renderizada de viewport iPhone não foi concluída. O navegador disponibilizado não expõe controle de viewport; prévia localhost e arquivo de inspeção foram bloqueados pelas políticas do ambiente. Não se declara teste em iPhone/Safari nem captura mobile realizada.
- Falha de rede e de contrato meteorológico foi verificada nos testes; o estado público disponível é ausência de token. Não houve interrupção deliberada de produção para simular indisponibilidade do provedor.
- Precipitação acumulada observada não é fornecida pelo contrato `current` consultado. Fuso de horário sem offset e hora de emissão da previsão não foram presumidos.

Publicação e desktop verificados; validação integral depende de ativação da API oficial e inspeção mobile. O clima não altera MPHI v1.0.
