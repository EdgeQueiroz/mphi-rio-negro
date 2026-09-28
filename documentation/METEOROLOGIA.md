# Meteorologia contextual: MET Norway e Climatempo

## Fonte ativa sem credencial

O workflow meteorológico consulta a API pública **Locationforecast 2.0 / compact** do Instituto Meteorológico da Noruega, em HTTPS, para o centro urbano de Manaus (`-3.1190, -60.0217`). A fonte disponibiliza uma previsão global baseada em modelo numérico, incluindo previsão horária de temperatura, umidade, vento e condição, além de precipitação prevista e cinco dias de resumo. O `meta.updated_at` é o horário de emissão do modelo; o `time` da série é o horário de validade da estimativa. **Nenhum desses campos equivale à observação de uma estação em Manaus ou à medição no Uiara.**

O produto global `compact` consultado para Manaus não disponibiliza sensação térmica, probabilidade de chuva nem chuva acumulada *observada*. Os valores permanecem `null`/`—`; não se fabrica sensação térmica a partir de temperatura, nem se trata uma previsão de chuva como observação. As mínimas/máximas vêm dos pontos temporais disponíveis; os totais de precipitação resultam da soma das menores janelas sem sobreposição. Onde uma janela de seis horas cruza meia-noite local, seu volume é repartido proporcionalmente pelo tempo: **aproximação de agregação**, sem precisão horária observada. O total de hoje considera somente as horas futuras a partir da coleta.

A origem exige identificação no `User-Agent` e atribuição. O coletor usa o endereço público do projeto como contato; a página credita **MET Norway**, aponta a API e a [licença CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). As consultas ocorrem no GitHub Actions, não no navegador do visitante. O coletor preserva `Expires` e `Last-Modified`, respeita validade de cache e usa `If-Modified-Since`; uma resposta 304 mantém o último dado e não adiciona snapshot fictício ao histórico. A coleta ocorre em quatro horários espaçados por dia. Em caso de indisponibilidade, mantém o último dado válido com indicação de atraso/falha.

Documentação primária: [serviço](https://api.met.no/weatherapi/locationforecast/2.0/documentation), [modelo global](https://docs.api.met.no/doc/locationforecast/datamodel.html), [formato JSON](https://docs.api.met.no/doc/ForecastJSON.html), [termos](https://docs.api.met.no/doc/TermsOfService.html) e [licença](https://docs.api.met.no/doc/License.html). Os modelos globais têm resolução geográfica limitada e não representam a chuva de toda a bacia do Rio Negro.

## Climatempo como fonte prioritária opcional

Se `CLIMATEMPO_TOKEN` estiver presente como secret no GitHub Actions, o workflow tenta primeiro a integração oficial Climatempo Advisor descrita em [CLIMATEMPO.md](CLIMATEMPO.md). Resposta válida completa assume a fonte; resposta parcial preserva dados Climatempo anteriores; indisponibilidade ou resposta parcial durante a troca de fonte recorre a uma fotografia completa do MET. Os registros de histórico guardam `source` e não se combinam blocos de fontes diferentes na visualização. Nenhuma chave é publicada.

## Isolamento e validação

`scripts/collect_weather.py` seleciona a fonte; `scripts/update_met.py` normaliza e grava os três arquivos `docs/data/weather_*.json`; `scripts/update_weather.py` permanece como adaptador Climatempo. Nenhum script importa o modelo MPHI. O histórico é append-only e cada fotografia distingue horário de recepção, emissão e validade da previsão. O workflow só comita os três arquivos meteorológicos e verifica que os arquivos hidrológicos não mudaram; o deploy do GitHub Pages confere os JSON públicos. A presença de uma previsão climática não autoriza inferência causal nem muda score, classificação, projeção, envelope, persistência ou validação da versão MPHI v1.0.

Teste offline: `python -m unittest discover -s tests_weather -v` e `node --test tests_weather/test_frontend.cjs`. A primeira execução pública com a API MET é aferida pelo estado `weather_status.json` e por `weather_latest.json`, sem preencher dados inventados.
