# Task 6 report — Camada técnica, três listas e aceite “menor é melhor”

## Status

Done. Lista ① SET of 10 matches Excel fixture. First three: BRSR6, SBSP3, RECV3.

## Commit

`cb00fe5` feat: sinal técnico e as três listas Top 10

Files: `src/venda_de_put/models.py`, `scoring.py`, `config.py`, `data/config.json`, `tests/test_scoring_lists.py`

## Tests

- `pytest tests/test_scoring_lists.py tests/test_scoring_ranks.py -v` — 7 passed
- Full suite `pytest -q` — 23 passed

## Implementation

- `AppConfig`, `TechnicalInput`, `ScoredAsset`, `Lists` in `models.py`
- `config.py`: `load_config` / `save_config`; re-exports `AppConfig`
- `apply_technical`: tendência alta/fora; Timing ENTRADA; SINAL `► VENDER PUT` or `—`; ScoreT/ScoreC/IV-HV as spec
- `build_lists`: ① 10 menores `pct_f` (tie ticker); ② 10 menores `score_t`; ③ `score_c` present (may be empty)

## Self-review

- SINAL strings exact.
- Defaults match Excel/brief (ifr 10–50, folga 0.05, meta 0.0115).
- No sources/scrape.
- Timing when not ENTRADA is `None` (spec only names ENTRADA).
- `AppConfig` tuples for scrape_times/fundamentus_days (JSON lists).

## Concerns

None blocking. Tie order among CMIN3/PSSA3/VIVA3 is alphabetical, not Excel ROW.

---

## Review fix — timing `"aguardar"`

### Finding

When IFR, preço and boll_inf exist and the ENTRADA condition fails, timing must be `"aguardar"`, not `None`. SINAL stays `"—"` when tendência and timing are calculable.

### TDD / fix evidence

1. Spec (`PROMPT-PLANEJAMENTO.md` / `PROMPT-DASHBOARD.md`): Timing = `"ENTRADA"` if band+folga; else `"aguardar"`.
2. Bug: `apply_technical` else-branch set `timing = None`.
3. Fix: `else: timing = "aguardar"` in `src/venda_de_put/scoring.py`.
4. Test: `test_timing_aguardar_when_entrada_fails_with_inputs_present` — IFR 70 out of band, all three inputs present → `timing == "aguardar"`, `sinal == "—"`. ITUB4 case also asserts `timing == "ENTRADA"` with recuo + fora (sinal still `"—"`).

### Test output

```
python -m pytest tests/test_scoring_lists.py tests/test_scoring_ranks.py -v
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1
collected 8 items

tests/test_scoring_lists.py::test_itub4_cached_excel_is_fora_not_sinal PASSED
tests/test_scoring_lists.py::test_sinal_aceso_entra_lista_combinada PASSED
tests/test_scoring_lists.py::test_timing_aguardar_when_entrada_fails_with_inputs_present PASSED
tests/test_scoring_lists.py::test_lista1_top_equals_excel_fixture PASSED
tests/test_scoring_ranks.py::test_financeiro_computes_nmrgl_and_skips_nroic PASSED
tests/test_scoring_ranks.py::test_menor_e_melhor_no_topo PASSED
tests/test_scoring_ranks.py::test_pl_negativo_vai_para_o_fim PASSED
tests/test_scoring_ranks.py::test_paridade_brsr6_itub4_contra_excel PASSED

============================== 8 passed in 0.06s ==============================
```
