# Referências sazonais do MPHI — Manaus 14990000

**Revisão:** 2026-10-29. **Tipo:** rastreabilidade de dados; não altera o algoritmo, os registros congelados ou os parâmetros de modelos experimentais.

## Fonte histórica e método

O indicador sazonal do MPHI usa o primeiro quartil (Q1, percentil 25%) e a mediana (percentil 50%) de cotas em metros, agrupadas por **mês do calendário**, para uma comparação de posição sazonal. Não é previsão nem nível de segurança operacional.

Para completar meses ausentes (01 a 07 e 11 a 12), foram utilizados valores derivados da série histórica da estação **Manaus 14990000, Rio Negro**, disponibilizada pela ANA via HidroWeb e preparada em formato CSV pelo projeto independente Data4ThePeople/RiverLevels-public.

- Fonte primária declarada: Agência Nacional de Águas e Saneamento Básico (ANA), HidroWeb, estação 14990000: https://www.snirh.gov.br/hidroweb/serieshistoricas
- Espelho transformado auditado: https://github.com/Data4ThePeople/RiverLevels-public/blob/main/data/processed/amazon-manaus.csv
- Metadados e ressalvas da transformação: https://github.com/Data4ThePeople/RiverLevels-public/blob/main/data/processed/amazon-manaus.json
- SHA-256 dos bytes CSV auditados em 29/10/2026: `d677f8c93cd1898bdb572742f2ac4e7ba143a189d8469636be7a916f6b921742`.
- Auditoria reproduzível: `.github/workflows/mphi-seasonal-audit.yml`; execução com 12 meses: https://github.com/EdgeQueiroz/mphi-rio-negro/actions/runs/40888582313

**Cohort selecionada:** observações diárias entre 01/01/1903 e 31/12/2025; registros efetivamente disponíveis por mês, sem preenchimento de lacunas. O conjunto contém medições históricas consistidas até 2014 e, depois, valores de telemetria classificados como provisórios pelo mantenedor do CSV. Portanto é uma série derivada da ANA, mas sua transformação por terceiro não corresponde a certificação oficial de quartis pela ANA.

**Cálculo:** ordenar as cotas diárias do mês em ordem crescente; para um percentil `p`, interpolar linearmente a posição `(n-1)*p`; dividir valores originais em centímetros por 100 e arredondar a duas casas decimais para a régua em metros. Não comparar cotas de réguas diferentes sem conciliar datum.

## Referências mensais atuais

| Mês | Q1 (m) | Mediana (m) | Estado |
|---|---:|---:|---|
| 01 | 20,37 | 21,44 | Completado em 29/10/2026 |
| 02 | 22,02 | 22,82 | Completado em 29/10/2026 |
| 03 | 23,12 | 24,28 | Completado em 29/10/2026 |
| 04 | 24,77 | 25,75 | Completado em 29/10/2026 |
| 05 | 26,40 | 27,23 | Completado em 29/10/2026 |
| 06 | 27,16 | 27,95 | Completado em 29/10/2026 |
| 07 | 26,76 | 27,65 | Completado em 29/10/2026 |
| 08 | 24,79 | 26,07 | Preexistente, inalterado |
| 09 | 20,59 | 22,64 | Preexistente, inalterado |
| 10 | 17,39 | 18,63 | Preexistente, inalterado |
| 11 | 17,36 | 18,41 | Completado em 29/10/2026 |
| 12 | 18,64 | 19,79 | Completado em 29/10/2026 |

Os valores dos meses 08 a 10 foram preservados byte a byte na atualização de `docs/data/latest.json`. A auditoria do CSV externo encontrou para eles valores próximos, **mas não idênticos**: não há prova de identidade da coorte/metodologia de origem desses três valores. Uma harmonização histórica futura exigiria revisão metodológica específica e avaliação de impacto; não é parte desta correção.

## Condições de segurança e verificação

1. Nenhum quartil foi inventado para o ambiente operacional. Os valores novos resultam das observações disponíveis da série histórica citada.
2. `seasonal_score(..., required=True)` continua exigindo referência válida; não foi criado fallback silencioso nem substituição por zero.
3. Uma previsão já emitida no `forecast_ledger.json` ou `hydrologic_ledger.json` não deve ser reescrita.
4. A atualização é aditiva ao objeto `seasonal` de `docs/data/latest.json`; não altera `current`, `series`, `projections` e horários de observação ao registrar as referências.
5. Validar novo processamento e publicação no GitHub Actions antes de declarar o incidente encerrado; medir impacto prospectivamente com a ADC.
6. A cobertura do calendário com Q1/mediana não substitui análises de risco, cotas de navegação, licenças nem acompanhamento das leituras oficiais do Porto.
