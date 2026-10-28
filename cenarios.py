"""Cenarios prontos para a demonstracao (os caminhos sao relativos a raiz do projeto)."""

CENARIOS = [
    {"titulo": "Superaquecimento (imagem + telemetria + texto)",
     "texto": "Estou na estrada e acendeu essa luz vermelha no painel. Posso continuar ate a proxima cidade?",
     "imagem": "exemplos/painel_superaquecimento.png", "csv": "exemplos/telemetria_superaquecimento.csv"},
    {"titulo": "Falha de ignicao (texto com codigo + telemetria + imagem)",
     "texto": "O carro esta tremendo quando paro no semaforo e o scanner mostrou o codigo P0300. O que pode ser?",
     "imagem": "exemplos/painel_injecao.png", "csv": "exemplos/telemetria_falha_ignicao.csv"},
    {"titulo": "Bateria/alternador (imagem + telemetria)",
     "texto": "Luz vermelha acesa e o radio desligou sozinho.",
     "imagem": "exemplos/painel_bateria.png", "csv": "exemplos/telemetria_bateria.csv"},
    {"titulo": "Tratamento de erro (CSV invalido + imagem corrompida)",
     "texto": "Segue o log do meu carro, ele esta esquentando.",
     "imagem": "exemplos/imagem_corrompida.png", "csv": "exemplos/telemetria_invalida.csv"},
    {"titulo": "Divergencia entre fontes (luz de temperatura + telemetria normal)",
     "texto": "A luz de temperatura acendeu, mas o carro parece normal.",
     "imagem": "exemplos/painel_superaquecimento.png", "csv": "exemplos/telemetria_normal.csv"},
    {"titulo": "Fora do escopo (somente texto)",
     "texto": "Qual a receita de um bolo de cenoura?"},
]
