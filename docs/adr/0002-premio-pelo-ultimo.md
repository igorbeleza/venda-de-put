# Taxa de entrada = último / strike

A meta do vencimento tem de ser atingida com a maior segurança (menor strike OTM). A taxa é o último negócio sobre o strike, e só conta put com volume na sessão.

Bid some depois do leilão e em série ilíquida; mid é otimista. Último sem volume é negócio velho (ex.: BRAVU122 a 0,27) e “bate” a meta no fundo da cadeia. `put.bs.bid` é a call — usar isso escolhe sempre o strike mais longe com taxa falsa.

Exemplo canônico: BRAV3 18/09/2026, meta 1,21% → BRAVU162 0,19/16,13 = 1,18% fora; BRAVU165 0,22/16,38 = 1,34% entra.
