# Livraria - versão web (MVP)

Versão web adaptada do projeto desktop Python/Tkinter/SQLite. Inclui login, consulta/pesquisa de estoque, cadastro de livros, movimentação de entrada/saída e criação de usuários por administradores.

## Executar localmente (Windows)

1. Instale Python 3.10 ou superior.
2. Abra o terminal nesta pasta.
3. Execute:

```bash
py -m venv .venv
.venv\\Scripts\\activate
py -m pip install -r requirements.txt
py app.py
```

4. Abra http://127.0.0.1:5000

Acesso inicial de demonstração: `admin` / `admin123` ou `estoque` / `estoque123`.

## Publicação

A aplicação está preparada para iniciar com Gunicorn (`Procfile`). Antes de publicar:

- Defina `SECRET_KEY` como uma chave longa e aleatória.
- Defina `DATABASE_PATH` para um caminho em disco persistente fornecido pela hospedagem. SQLite em armazenamento efêmero pode perder os dados quando a instância reiniciar ou for recriada.
- Troque as senhas iniciais de demonstração. O MVP ainda não inclui tela para alterar senha.
- Configure HTTPS e restrinja o acesso conforme a necessidade da livraria.

A rota `/saude` responde `{"status":"ok"}` e pode ser usada como health check.

## Observação

Esta é uma nova interface web; o arquivo desktop original `estoque_livraria.py` permanece separado e não é alterado. A versão web reutiliza as mesmas entidades e regras principais, mas ainda precisa de testes funcionais e validação em ambiente de hospedagem antes de ser considerada produção.
