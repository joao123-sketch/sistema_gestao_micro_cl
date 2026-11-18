"""
Servidor MCP local (stdio) do Sistema de Gestão de Atividades.

Expõe as atividades (e seus passos) do sistema como ferramentas MCP, para
serem usadas pelo Claude. Autentica-se no Flask com um login e senha fixos,
informados por variável de ambiente, e mantém a sessão autenticada durante
toda a execução.

Variáveis de ambiente:
    GESTAO_ATIVIDADES_URL    Base do sistema Flask (padrão: instância compartilhada no PythonAnywhere)
    GESTAO_ATIVIDADES_LOGIN  Seu login de usuário já cadastrado (ex.: "edu")
    GESTAO_ATIVIDADES_SENHA  Sua senha desse usuário

Cada pessoa do time roda esse servidor localmente (via .mcp.json), com
seu próprio login/senha, apontando para a mesma instância hospedada —
por isso todo mundo mexe nos mesmos dados.

Para conectar direto pelo Claude (Configurações → Conectores), sem rodar
nada localmente, veja mcp_http_server.py — a versão hospedada, com login
via OAuth em vez de senha fixa por variável de ambiente.
"""

import os

import requests
from mcp.server.mcpserver import MCPServer

from mcp_tools import FLASK_BASE_URL_PADRAO, registrar_ferramentas

BASE_URL = os.environ.get('GESTAO_ATIVIDADES_URL', FLASK_BASE_URL_PADRAO).rstrip('/')
LOGIN = os.environ.get('GESTAO_ATIVIDADES_LOGIN')
SENHA = os.environ.get('GESTAO_ATIVIDADES_SENHA')

mcp = MCPServer("gestao-atividades")

_session = requests.Session()
_autenticado = False


def _garantir_login():
    global _autenticado
    if _autenticado:
        return
    if not LOGIN or not SENHA:
        raise RuntimeError(
            "Defina GESTAO_ATIVIDADES_LOGIN e GESTAO_ATIVIDADES_SENHA nas "
            "variáveis de ambiente do servidor MCP para ele conseguir entrar "
            "no sistema de Gestão de Atividades."
        )
    resp = _session.post(f'{BASE_URL}/login', data={'login': LOGIN, 'senha': SENHA}, timeout=10)
    resp.raise_for_status()
    if resp.url.rstrip('/').endswith('/login'):
        raise RuntimeError("Login ou senha inválidos para o sistema de Gestão de Atividades.")
    _autenticado = True


def _obter_sessao() -> requests.Session:
    _garantir_login()
    return _session


registrar_ferramentas(mcp, _obter_sessao, BASE_URL)


if __name__ == '__main__':
    mcp.run()
