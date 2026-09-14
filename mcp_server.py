"""
Servidor MCP do Sistema de Gestão de Atividades.

Expõe as atividades (e seus passos) do sistema como ferramentas MCP,
para serem usadas pelo Claude. Autentica-se no Flask com um login e
senha fixos, informados por variável de ambiente, e mantém a sessão
autenticada durante toda a execução.

Variáveis de ambiente:
    GESTAO_ATIVIDADES_URL    Base do sistema Flask (padrão: instância compartilhada no PythonAnywhere)
    GESTAO_ATIVIDADES_LOGIN  Seu login de usuário já cadastrado (ex.: "edu")
    GESTAO_ATIVIDADES_SENHA  Sua senha desse usuário

Cada pessoa do time roda esse servidor localmente (via .mcp.json), com
seu próprio login/senha, apontando para a mesma instância hospedada —
por isso todo mundo mexe nos mesmos dados.
"""

import os

import requests
from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get('GESTAO_ATIVIDADES_URL', 'https://victorjoao271828.pythonanywhere.com').rstrip('/')
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


def _get(path, **kwargs):
    _garantir_login()
    r = _session.get(f'{BASE_URL}{path}', timeout=10, **kwargs)
    r.raise_for_status()
    return r.json()


def _post(path, **kwargs):
    _garantir_login()
    r = _session.post(f'{BASE_URL}{path}', timeout=10, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


def _delete(path, **kwargs):
    _garantir_login()
    r = _session.delete(f'{BASE_URL}{path}', timeout=10, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


# ── Atividades ──────────────────────────────────────────────

@mcp.tool()
def listar_atividades(arquivado: bool = False, responsavel: str = "", status: str = "", busca: str = "") -> list:
    """Lista as atividades do sistema.

    arquivado: False para ativas (padrão), True para arquivadas.
    responsavel: filtra pelo nome exato do responsável (ex.: "Edu").
    status: filtra pelo status exibido (Pendente, Em andamento, Feito, Atrasado).
    busca: filtra atividades cujo título contenha esse texto.
    """
    params = {'arquivado': '1' if arquivado else '0'}
    if responsavel:
        params['responsavel'] = responsavel
    if status:
        params['status'] = status
    if busca:
        params['q'] = busca
    return _get('/api/atividades', params=params)


@mcp.tool()
def obter_atividade(atividade_id: int) -> dict:
    """Retorna os detalhes de uma atividade (inclui % de execução dos passos)."""
    return _get(f'/api/atividades/{atividade_id}/painel_geral')


@mcp.tool()
def criar_atividade(area: str, atividade: str, responsavel: str, status: str = "Pendente",
                     prazo: str = "", data_inicio: str = "", prioridade: str = "Baixa") -> dict:
    """Cria uma nova atividade.

    Datas no formato AAAA-MM-DD (se omitidas, usa a data de hoje).
    status: Pendente, Em andamento ou Feito. prioridade: Baixa, Média ou Alta.
    """
    corpo = {'area': area, 'atividade': atividade, 'responsavel': responsavel,
             'status': status, 'prioridade': prioridade}
    if prazo:
        corpo['prazo'] = prazo
    if data_inicio:
        corpo['data_inicio'] = data_inicio
    return _post('/api/atividades', json=corpo)


@mcp.tool()
def editar_atividade(atividade_id: int, area: str = "", atividade: str = "", responsavel: str = "",
                      status: str = "", prazo: str = "", data_inicio: str = "", prioridade: str = "",
                      observacoes: str = "") -> dict:
    """Edita campos de uma atividade existente. Envie só os campos que quer alterar."""
    corpo = {k: v for k, v in {
        'area': area, 'atividade': atividade, 'responsavel': responsavel, 'status': status,
        'prazo': prazo, 'data_inicio': data_inicio, 'prioridade': prioridade, 'observacoes': observacoes,
    }.items() if v}
    if not corpo:
        return {'status': 'error', 'mensagem': 'Nenhum campo informado para editar.'}
    return _post(f'/api/atividades/{atividade_id}/editar', json=corpo)


@mcp.tool()
def arquivar_atividade(atividade_id: int) -> dict:
    """Arquiva uma atividade, tirando-a da lista de ativas."""
    return _post(f'/api/atividades/{atividade_id}/arquivar')


@mcp.tool()
def restaurar_atividade(atividade_id: int) -> dict:
    """Restaura uma atividade arquivada de volta para a lista de ativas."""
    return _post(f'/api/atividades/{atividade_id}/restaurar')


@mcp.tool()
def deletar_atividade(atividade_id: int) -> dict:
    """Apaga uma atividade permanentemente. Ação irreversível — prefira arquivar_atividade."""
    return _delete(f'/api/atividades/{atividade_id}')


# ── Passos ───────────────────────────────────────────────────

@mcp.tool()
def listar_passos(atividade_id: int) -> list:
    """Lista os passos/etapas de uma atividade."""
    return _get(f'/api/atividades/{atividade_id}/passos')


@mcp.tool()
def adicionar_passo(atividade_id: int, descricao: str, prazo: str = "", responsavel: str = "") -> dict:
    """Adiciona um novo passo/etapa a uma atividade."""
    return _post('/api/passos/adicionar', data={
        'atividade_id': atividade_id, 'descricao': descricao, 'prazo': prazo, 'responsavel': responsavel,
    })


@mcp.tool()
def concluir_passo(passo_id: int, concluido: bool = True) -> dict:
    """Marca um passo como concluído (ou volta a pendente, com concluido=False).

    Quando todos os passos de uma atividade ficam concluídos, o status
    da atividade muda automaticamente para "Feito".
    """
    return _post(f'/api/passos/{passo_id}/toggle', data={'concluido': 'true' if concluido else 'false'})


@mcp.tool()
def excluir_passo(passo_id: int) -> dict:
    """Remove um passo de uma atividade."""
    return _post(f'/api/passos/{passo_id}/excluir')


if __name__ == '__main__':
    mcp.run()
