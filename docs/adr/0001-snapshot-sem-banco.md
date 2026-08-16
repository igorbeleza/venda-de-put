# Snapshot em disco, sem banco

O dashboard é leitura de um JSON gravado pelo scrape. Refresh relê o arquivo.

Um banco ou um cache vivo faria o botão Atualizar parecer “tempo real” e empurraria scrape para o request. O seletor de vencimento precisa de todas as séries já no snapshot; persistir o JSON cru do OpLab estoura disco. O arquivo pequeno (puts enxutas) é o que torna a troca de vencimento instantânea.
