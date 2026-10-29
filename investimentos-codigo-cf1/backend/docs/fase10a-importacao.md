# Fase 10a — Importação CSV/XLSX/OFX + Deduplicação Exata

## Confirmações pré-implementação (pedidas antes de codificar)

1. **Mapeamento de arquivos**: ver seção "Arquivos criados/alterados" abaixo — bateu com o planejado na proposta refinada.
2. **Dependências**: `openpyxl` (leitura de XLSX), `ofxparse` (parsing de OFX), `python-multipart` (obrigatório para o FastAPI aceitar upload de arquivo — não estava listado na proposta, descoberto ao implementar o endpoint; CSV usa só a biblioteca padrão do Python).
3. **Transação atômica**: implementada reaproveitando o mecanismo já existente do `get_db` (commit só se o request inteiro terminar sem exceção, rollback caso contrário) — o `commit_import` nunca chama `commit()`/`rollback()` diretamente, só deixa a exceção propagar. Isso é o mesmo mecanismo que já garantia a atomicidade de `create_transfer` desde a Fase 6.
4. **Proteção do HMAC**: `settings.import_hmac_secret`, nunca devolvido em nenhuma resposta da API, lido de variável de ambiente em produção (valor default é só para desenvolvimento, documentado no próprio código).
5. **Separação parser/orquestração**: cada parser (`csv_parser.py`, `xlsx_parser.py`, `ofx_parser.py`) é puro — bytes entram, `ParsedRow` sai, nenhum toca banco. `import_service.py` é quem resolve `asset_id`, calcula `external_reference`, checa duplicidade e assina/verifica o HMAC.

## Arquivos criados/alterados

```
app/services/imports/common.py       (novo) ParsedRow, mapeamento de tipos, validações compartilhadas
app/services/imports/csv_parser.py   (novo)
app/services/imports/xlsx_parser.py  (novo)
app/services/imports/ofx_parser.py   (novo) — só extrato bancário (STMTTRN), investimento fora do escopo
app/services/import_service.py       (novo) orquestração completa
app/schemas/imports.py               (novo) ImportRow, ImportPreviewResponse, ImportCommitRequest, ImportCommitResult
app/api/routers/imports.py           (novo) POST /imports/preview, POST /imports/commit
app/services/transaction_service.py  (alterado, D-G2) — extraído `_insert_transaction` (compartilhado);
                                      `_check_sell_against_position` generalizada para argumentos discretos;
                                      nova função pública `create_imported_transaction` (interna ao sistema,
                                      não exposta como endpoint próprio); `create_transaction` (MANUAL,
                                      `POST /transactions`) permanece com o mesmo comportamento externo
app/services/exceptions.py           (alterado) + ImportParsingError, InvalidImportSignatureError, ImportRowRejectedError
app/core/config.py                   (alterado) + import_hmac_secret
app/main.py                          (alterado) registra o router de imports
pyproject.toml                       (alterado) + openpyxl, ofxparse, python-multipart
```

Nenhum model, migration ou trigger foi tocado. `PositionCalculator`, `profitability_service`, `dashboard_service`, `dividends_service` não foram alterados. Frontend não foi alterado.

## Decisões implementadas

- **D-G1**: só Fase 10a — deduplicação exata (índice único já existente desde a Fase 4) + `possible_duplicate` como alerta informativo. Reconciliation Engine fuzzy/`ReconciliationLog` **não implementados** (Fase 10b).
- **D-G2**: `POST /transactions` inalterado (confirmado pelos testes existentes, todos passando sem modificação) — importação usa `create_imported_transaction`, que reaplica `_get_owned_account` e `_check_sell_against_position` exatamente como a criação manual.
- **D-G3**: CSV, XLSX, OFX implementados. PDF fora do escopo.
- **D-G4 com o refinamento**: OFX usa `FITID` nativo. CSV/XLSX usam `SHA-256(conta+data+tipo+asset_id+quantidade+preço+taxas+valor+moeda) + índice de ocorrência dentro do lote` — testado que duas linhas idênticas no mesmo arquivo são ambas importadas (índices de ocorrência diferentes), e que reimportar o mesmo arquivo é pego pela duplicidade exata (mesma sequência de índices reproduzida).
- **Preview → commit com HMAC-SHA256**: sem tabela, sem cache, sem Redis — testado que um payload alterado após a preview é rejeitado (`409`).
- **Ordem cronológica**: garantida na preview e novamente no commit (defesa em profundidade) — testado com uma `SELL` que aparece primeiro no arquivo mas tem data posterior à `BUY`, aceita corretamente.
- **Commit tudo-ou-nada**: uma linha inválida (ex.: `SELL` acima da posição) reverte o lote inteiro — testado, inclusive um cenário de erro de persistência inesperado (colisão forçada de `external_reference`) revertendo tudo.

## Testes executados (156 no total, 27 novos)

**Puros** (`tests/services/test_import_parsers.py`, 10, sem banco): CSV válido, coluna obrigatória ausente, tipo desconhecido, `COMPRA` sem ativo, data inválida, arquivo vazio; XLSX válido, linha em branco ignorada; OFX válido (`FITID` como referência), arquivo inválido.

**Integração com banco** (`tests/services/test_import_service.py`, 12): preview não grava nada; lote 100% válido gravado por completo; **tudo-ou-nada** (uma linha inválida reverte tudo; erro inesperado de persistência reverte tudo); duas linhas idênticas no mesmo lote ambas importadas; reimportação do mesmo arquivo detecta duplicata exata; manual + importação equivalente marca `possible_duplicate`; payload alterado rejeitado pelo HMAC; inclusão/exclusão seletiva de linhas; `SELL` fora de ordem no arquivo mas cronologicamente válida aceita; regressão financeira (importação produz a mesma posição que lançamento manual equivalente); isolamento de usuário.

**API** (`tests/api/test_imports_api.py`, 5): upload multipart real gera preview; preview→commit completo grava e aparece no histórico; assinatura adulterada rejeitada (`409`); formato inválido rejeitado (`400`); conta de outro usuário rejeitada (`404`).

**Suíte completa de backend: 156 testes passando** (129 anteriores intactos + 27 novos). **Frontend: 16 testes confirmados intactos** (nenhum arquivo tocado).

## Lint/format

`ruff check .` e `black --check .` limpos.

## Dívidas técnicas e achados durante a implementação

- **`python-multipart` não estava na proposta** — descoberto ao implementar o endpoint de upload (é um requisito do próprio FastAPI para `UploadFile`/`Form`, não uma escolha de design). Adicionado e documentado aqui, não silenciado.
- **Refatoração em `transaction_service.py`** (extração de `_insert_transaction`, generalização de `_check_sell_against_position`): mínima e estritamente necessária para cumprir D-G2 — validada pela suíte de testes da Fase 6 (`test_transaction_service.py`, `test_transactions_api.py`) continuando 100% verde sem nenhuma alteração nela.
- **Limitação conhecida e documentada** (já prevista na proposta): duplicidade entre fontes diferentes ou entre lotes de importação diferentes (ex.: reimportar um extrato com sobreposição parcial de período) não é detectável por hash — só `possible_duplicate` alerta, sem bloquear. Fica para a Fase 10b.
- **Escopo do parser OFX**: só extratos bancários (`STMTTRN`) — OFX de investimento (`BUYSTOCK`/`SELLSTOCK`) não é suportado nesta fase (exigiria mapear `CUSIP`/identificadores de ativo que não temos). Documentado no próprio código do parser.
- **Formato fixo de CSV/XLSX**: colunas documentadas (`data`, `tipo`, `ativo`, `quantidade`, `preco_unitario`, `taxas`, `valor`, `moeda`) — não há detecção automática de layout de corretora nesta fase (seria um escopo bem maior, não solicitado).
- **Resolução de ativo por ticker**: feita por `Asset.ticker` diretamente (sem considerar país) — se dois ativos de países diferentes compartilharem o mesmo ticker no catálogo, a resolução pode ser ambígua. Não é um problema na base de dados atual, mas registro como ponto de atenção caso o catálogo cresça com ativos internacionais.

## Confirmação

**Nenhuma fase posterior foi iniciada.** PDF, Reconciliation Engine fuzzy, `ReconciliationLog`, frontend e Fase 11 não foram tocados. Nenhuma decisão das Fases 4–9 foi alterada.
