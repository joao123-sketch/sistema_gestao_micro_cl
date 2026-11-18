"""
Servidor MCP remoto (HTTP + OAuth 2.1) do Sistema de Gestão de Atividades.

Pensado para ser hospedado junto com o Flask no PythonAnywhere e conectado
direto pelo Claude em Configurações → Conectores — sem precisar rodar nada
localmente nem guardar senha em variável de ambiente.

Fluxo: o Claude se registra dinamicamente (RFC 7591), manda o usuário para
/oauth/login, que pede o login/senha já cadastrados no sistema e (por trás)
faz o login de verdade em {GESTAO_ATIVIDADES_URL}/login. A partir daí o
Claude guarda um access token opaco (emitido por mcp_oauth_provider.py) e o
usa em cada chamada de ferramenta — toda a lógica de negócio continua em
app.py, chamada via a API JSON já existente.

Este arquivo só define o app ASGI; quem expõe ele por WSGI no PythonAnywhere
é wsgi_combined.py — veja lá as instruções de deploy.
"""

import html
import os

import requests
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp_oauth_provider import (
    FLASK_BASE_URL,
    GestaoOAuthProvider,
    autenticar_no_flask,
    carregar_pendencia,
    concluir_login,
    init_oauth_db,
)
from mcp_tools import registrar_ferramentas

init_oauth_db()

ISSUER_URL = os.environ.get('GESTAO_MCP_ISSUER_URL', FLASK_BASE_URL).rstrip('/')
RESOURCE_URL = f'{ISSUER_URL}/mcp'

mcp = MCPServer(
    'gestao-atividades',
    auth_server_provider=GestaoOAuthProvider(),
    auth=AuthSettings(
        issuer_url=ISSUER_URL,
        resource_server_url=RESOURCE_URL,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=['atividades'],
            default_scopes=['atividades'],
        ),
        revocation_options=RevocationOptions(enabled=True),
        validate_token_resource=True,
    ),
)


def _obter_sessao() -> requests.Session:
    token = get_access_token()
    cookie = (token.claims or {}).get('flask_cookie') if token else None
    if not token or not cookie:
        raise RuntimeError('Não autenticado.')
    sessao = requests.Session()
    sessao.cookies.set('session', cookie)
    return sessao


registrar_ferramentas(mcp, _obter_sessao, FLASK_BASE_URL)


# ── Tela de login do fluxo OAuth ────────────────────────────────

_LOGIN_PAGE = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Conectar ao Sistema de Gestão de Atividades</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#f4f5f7; display:flex; min-height:100vh;
         align-items:center; justify-content:center; margin:0; }}
  .card {{ background:#fff; padding:2rem; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,.08);
          width:100%; max-width:360px; box-sizing:border-box; }}
  h1 {{ font-size:1.15rem; margin:0 0 1.25rem; }}
  label {{ display:block; font-size:.85rem; margin-bottom:.25rem; color:#444; }}
  input {{ width:100%; padding:.55rem; margin-bottom:1rem; border:1px solid #ccc; border-radius:6px;
          box-sizing:border-box; font-size:1rem; }}
  button {{ width:100%; padding:.6rem; border:none; border-radius:6px; background:#2563eb; color:#fff;
           font-size:1rem; cursor:pointer; }}
  .erro {{ color:#b91c1c; font-size:.85rem; margin:0 0 1rem; }}
</style></head>
<body><div class="card">
<h1>Entrar no Sistema de Gestão de Atividades</h1>
{erro}
<form method="post">
<input type="hidden" name="txn" value="{txn}">
<label for="login">Login</label>
<input id="login" name="login" autocomplete="username" required autofocus>
<label for="senha">Senha</label>
<input id="senha" name="senha" type="password" autocomplete="current-password" required>
<button type="submit">Entrar e autorizar</button>
</form>
</div></body></html>"""

_SESSAO_EXPIRADA = (
    '<p style="font-family:system-ui,sans-serif;padding:2rem">'
    'Esta solicitação de autorização expirou ou é inválida. '
    'Feche esta aba e tente conectar novamente pelo Claude.</p>'
)


def _pagina_login(txn: str, erro: str = '') -> str:
    bloco_erro = f'<p class="erro">{html.escape(erro)}</p>' if erro else ''
    return _LOGIN_PAGE.format(txn=html.escape(txn), erro=bloco_erro)


@mcp.custom_route('/oauth/login', methods=['GET', 'POST'])
async def oauth_login(request: Request) -> Response:
    if request.method == 'GET':
        txn = request.query_params.get('txn', '')
        if carregar_pendencia(txn) is None:
            return HTMLResponse(_SESSAO_EXPIRADA, status_code=400)
        return HTMLResponse(_pagina_login(txn))

    form = await request.form()
    txn = str(form.get('txn', ''))
    login = str(form.get('login', '')).strip()
    senha = str(form.get('senha', ''))

    if carregar_pendencia(txn) is None:
        return HTMLResponse(_SESSAO_EXPIRADA, status_code=400)

    if not login or not senha:
        return HTMLResponse(_pagina_login(txn, 'Preencha login e senha.'), status_code=400)

    try:
        cookie = autenticar_no_flask(login, senha)
    except requests.RequestException:
        return HTMLResponse(
            _pagina_login(txn, 'Não foi possível falar com o sistema agora. Tente de novo em instantes.'),
            status_code=502,
        )

    if not cookie:
        return HTMLResponse(_pagina_login(txn, 'Login ou senha incorretos.'), status_code=401)

    destino = concluir_login(txn, login, cookie)
    if destino is None:
        return HTMLResponse(_SESSAO_EXPIRADA, status_code=400)
    return RedirectResponse(url=destino, status_code=302)


# App ASGI puro. wsgi_combined.py envolve isto com a2wsgi para rodar sob o
# WSGI do PythonAnywhere, ao lado do Flask.
app = mcp.streamable_http_app(json_response=True, stateless_http=True)
