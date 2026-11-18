"""
Ponto de entrada WSGI combinado, para hospedar no PythonAnywhere.

Expõe, no mesmo processo/domínio:
  - o Flask de sempre (app.py), em todas as rotas que já existem hoje;
  - o servidor MCP remoto com OAuth (mcp_http_server.py), só nas rotas que
    ele usa (/mcp, /authorize, /token, /register, /revoke, /oauth/login e
    os /.well-known/... de descoberta OAuth).

Depende de `a2wsgi` (pip install a2wsgi) além do que já está em
requirements.txt e requirements-mcp.txt — instale no mesmo virtualenv que
o PythonAnywhere usa para servir o site.

No arquivo de configuração WSGI do PythonAnywhere (aba Web → Code → WSGI
configuration file), troque o conteúdo por algo como:

    import sys
    caminho_projeto = '/home/SEU_USUARIO/sistema_gestao_atividades'
    if caminho_projeto not in sys.path:
        sys.path.insert(0, caminho_projeto)

    from wsgi_combined import application

Depois é só dar Reload no site.
"""

from app import app as _flask_app

# O servidor MCP só é carregado na primeira chamada a uma rota MCP. Assim o
# Flask nunca depende dele: se o MCP travar ou falhar ao importar, só as
# rotas MCP são afetadas e o sistema continua no ar.
_mcp_wsgi_app = None


def _obter_mcp_wsgi():
    global _mcp_wsgi_app
    if _mcp_wsgi_app is None:
        from a2wsgi import ASGIMiddleware
        from mcp_http_server import app as _mcp_asgi_app
        _mcp_wsgi_app = ASGIMiddleware(_mcp_asgi_app)
    return _mcp_wsgi_app


# Rotas que pertencem ao servidor MCP/OAuth; qualquer outra vai pro Flask.
_ROTAS_MCP_EXATAS = {'/mcp', '/authorize', '/token', '/register', '/revoke', '/oauth/login'}
_PREFIXOS_MCP = ('/.well-known/',)


def application(environ, start_response):
    caminho = environ.get('PATH_INFO', '')
    if caminho in _ROTAS_MCP_EXATAS or caminho.startswith(_PREFIXOS_MCP):
        return _obter_mcp_wsgi()(environ, start_response)
    return _flask_app(environ, start_response)
