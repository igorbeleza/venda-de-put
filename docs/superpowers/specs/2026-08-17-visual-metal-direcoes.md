# Direções visuais — metal (em deliberação)

Não é spec de implementação. Estaciona opções até o usuário escolher.

Escopo fixo em qualquer direção: oito abas, três listas, fita de prêmio-alvo, seletor de vencimento, “sem dado”, tema claro/escuro. Só muda pele.

## A + B — chapa usinada (guardada)

Pedido original interpretado como titânio de produto Apple. Usuário gostou e pediu para guardar.

- **A claro:** titânio natural (cinza quente, fosco, grão horizontal). Cards como placas fresadas. Latão só na fita do prêmio-alvo.
- **B escuro:** space black (grafite, filete de luz no chanfro). Mesma peça, outro acabamento.
- Tipo: grotesca seca + mono tabular. Sem Inter.
- Verde floresta vira esmalte (sinal / bate a meta), não “success green”.
- Não é foto de metal de fundo. É grão CSS, chanfro e número gravado.
- Estudos: sessão `images/2.jpg` (A), `images/1.jpg` (B). Alumínio C (`images/3.jpg`) ficou de fora.
- Mockup completo (não é o site ativo): [mockup-chapa-ab.html](mockup-chapa-ab.html)

## D — materiais do sistema iOS (aplicada no CSS)

Pele atual (`bui20`): D + A/B juntos — mesa de titânio, cromo de vidro, fita de latão no prêmio-alvo.

O “metal” que o usuário quis dizer: o cromo do iOS (Liquid Glass / materiais HIG), não titânio físico.

- Vidro líquido **só na camada de controle** (abas, sidebar, toolbar, botões). Conteúdo (cards, tabelas, narrativas) fica em material padrão opaco — HIG: não colocar Liquid Glass no conteúdo.
- Página: cinza de sistema (`#F2F2F7` claro / preto de sistema no escuro), não branco de SaaS.
- Cantos contínuos grandes, separadores finos, título grande, listas agrupadas.
- Brilho especular no vidro (o “metal” do iOS). Sem blur roxo, sem card de vidro em tudo.
- Acento: verde floresta como tint do app, não o azul de sistema da Apple.

Estudos de sessão: `images/5.jpg` (claro), `images/6.jpg` (escuro), `images/4.jpg` (cromo: vidro + disco de alumínio). Os prints inventam chrome e copy — o produto real mantém as oito abas e o vocabulário de CONTEXT.md.
