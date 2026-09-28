# MPHI — integração meteorológica contextual

## Invariante

O clima não integra MPHI v1.0, v1.1-shadow ou v2.0-hydrologic-alpha. Não existe importação do coletor meteorológico pelos motores nem leitura de `weather_*.json` no cálculo. Score, thresholds, persistência, projeções, envelopes e validação mantêm o código anterior. A interface apenas apresenta métricas já calculadas e desenha os horizontes existentes, sem gerar novas previsões.

## Fonte e contrato

Fonte preparada: **API oficial Climatempo Advisor v1**, via HTTPS. Referências consultadas em 28/09/2026:

- https://advisor.climatempo.com.br/
- https://apiadvisor.climatempo.com.br/doc/index.html
- https://apiadvisor.climatempo.com.br/doc/api_data.js
- https://github.com/StormGeo/advisor-sdk

Endpoints documentados:

- `GET /api/v1/locale/city?name=Manaus&state=AM&country=BR` — resolve ID sem adivinhação;
- `GET /api/v1/weather/locale/{id}/current` — temperatura °C, sensação °C, condição, umidade %, vento km/h/direção, pressão hPa, horário da observação;
- `GET /api/v1/forecast/locale/{id}/days/15` — contrato de previsão diária; preservamos hoje e os quatro dias seguintes disponíveis.

O token é passado somente no runner ao domínio fixo `https://apiadvisor.climatempo.com.br`, no parâmetro exigido pela API. Redirecionamentos são rejeitados. O corpo bruto e URLs autenticadas nunca são gravados nem logados. Somente campos selecionados e validados vão para o site. A consulta não registra cidade em plano/assinatura, não aceita contratos nem contrata produtos.

Manaus/AM é referência municipal inicial. Coordenadas do Uiara não foram presumidas; meteorologia local não representa chuva em toda a bacia. A Climatempo deve confirmar quais produtos, município, limites de requisição e direitos de exibição pública/armazenamento fazem parte do acesso contratado.

## Ativação

No repositório **EdgeQueiroz/mphi-rio-negro**:

1. Abrir **Settings → Secrets and variables → Actions → New repository secret**.
2. Criar **`CLIMATEMPO_TOKEN`** com o token oficial autorizado para `current` e `days/15` de Manaus. Pode também ser secret do ambiente `github-pages`.
3. Opcional: em **Variables**, definir `CLIMATEMPO_LOCALE_ID` com o ID retornado pela consulta oficial, evitando uma consulta de resolução por execução. A resposta continua obrigada a identificar Manaus/AM/BR.
4. Somente depois de confirmar com a Climatempo o fuso dos horários sem offset, definir a variável `CLIMATEMPO_SOURCE_TIMEZONE` com um identificador IANA (por exemplo `America/Manaus` se confirmado). Sem essa confirmação, o horário original é exibido com **fuso não informado**, e `observed_at` fica nulo.
5. Em **Actions → MPHI - contexto meteorológico Climatempo → Run workflow**, executar na branch `fileOrganizer`.
6. Conferir `weather_status.json`: `ok` ou `partial`, horários reais em `weather_latest.json`, nova entrada no histórico e confirmação pública no resumo da execução. Conferir a interface após atualização.

Não inserir a chave no JavaScript, HTML, JSON público, commits ou variáveis prefixadas para frontend. O histórico contém somente dados normalizados. A ausência de token gera `not_configured`; não cria valores meteorológicos sintéticos nem apaga a última leitura.

## Arquitetura e arquivos

- `scripts/update_weather.py`: coleta e normalização independente, timeout de conexão/leitura 5/15 s por chamada.
- `.github/workflows/update-weather.yml`: agenda independente às 05:23 / 11:23 / 17:23 / 23:23 em Manaus; oito chamadas de produtos/dia e, sem ID configurado, quatro resoluções de cidade. Rever periodicidade conforme franquia contratada. Sem retry imediato em 429; próxima execução realiza nova tentativa.
- `docs/data/weather_latest.json`: última seção válida de clima atual e previsão; horários individuais, localização, unidades explícitas.
- `docs/data/weather_status.json`: estado da última tentativa, erros genéricos sem conteúdo do provedor, agenda e prazo de atraso.
- `docs/data/weather_history.json`: snapshots recebidos append-only; registra timestamp de recebimento, localização, fonte e os blocos recebidos naquela execução. Em falha parcial, não apresenta o bloco antigo como recém-recebido. Histórico começa com a primeira coleta válida; não há preenchimento retroativo.
- `docs/weather.js`: módulo autônomo, com duas requisições locais `no-store`, parâmetro de atualização e timeout de 10 s. Não bloqueia `app.js`.
- `tests_weather/`: testes independentes; não são adicionados ao gate da coleta hidrológica existente.

Snapshots são preservados em cada coleta bem-sucedida (até quatro/dia), permitindo futuramente agregação diária, sem reescrever as previsões recebidas. IDs SHA-256 evitam duplicação de uma mesma captura. Escrita por arquivo temporário + rename; falha total altera apenas status. Falha de um endpoint preserva seu bloco anterior enquanto o outro pode avançar. A automação valida prefixo imutável do histórico e ausência de alterações nos arquivos hidrológicos.

A coleta meteorológica usa o mesmo grupo de concorrência da publicação existente. Isso serializa checkout/commit/deploy e evita uma publicação sobrescrever uma atualização hidrológica simultânea. A vigília longa pode atrasar o clima; o frontend explicita o atraso. A publicação meteorológica reaproveita o estado de consulta hidrológica mais recente já publicado quando corresponde à mesma medição, sem regravar o modelo. Não modifica o workflow hidrológico existente.

O GitHub Pages continua sendo a hospedagem. Ambos os workflows verificam os dados públicos após publicação. Arquivos de dados meteorológicos são persistidos antes do deploy, permitindo recuperação em uma execução posterior. Falha meteorológica não dispara nem cancela a coleta hidrológica.

## Ausência, validade e limites

- Dado ausente é `null`/`—`, nunca zero. Zero de chuva/probabilidade é válido.
- Temperaturas, umidade, vento e chuva têm validação numérica; cidade incorreta, estrutura inválida, datas repetidas, regressão de observação e observação explicitamente futura são rejeitadas.
- Regra de atraso contextual: **12 horas**, duas janelas esperadas de coleta. Não é prazo de validade científica universal. Horários de cada bloco ficam visíveis.
- Um horário sem fuso não é convertido silenciosamente. Observação de dia anterior recebe indicação conservadora de última condição disponível.
- Previsões expiradas não são apresentadas como próximos dias. Dados permanecem no histórico.
- Precipitação prevista é total diário estimado. **O endpoint `current` não fornece acumulado observado com período definido.** Esse campo permanece nulo. Não se soma previsão para fabricar chuva observada. Uma futura integração de produto histórico/observacional exige contrato e período confirmado.
- A API diária não informa hora de emissão no contrato consultado: `issued_at` é nulo; o recebimento é `collected_at`.
- A integração foi testada com fixtures sintéticas compatíveis com a documentação. A validação ao vivo da Climatempo depende de token/plano disponível no runner; os arquivos públicos registram esse resultado sem segredo.
- Correlação futura precisa separar observação, previsão e instante de disponibilidade, avaliar fora da amostra e respeitar o tempo de propagação da bacia. Correlação não prova causalidade. Uso preditivo exige nova versão e validação separada.

## Verificação

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests_weather -v
node --test tests_weather/test_frontend.cjs
node --check docs/app.js
node --check docs/weather.js
```

A referência inicial foi o commit `ea003b6376d0f1842f69821194dea0c690df2357`: 34 entradas no forecast ledger e 7 no ledger hidrológico. Nenhum JSON hidrológico foi incluído no commit de implementação. As atualizações normais futuras continuam autorizadas pela automação, preservando o prefixo histórico.
