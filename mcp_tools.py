"""
Definição das ferramentas MCP do Sistema de Gestão de Atividades.

Compartilhada pelos dois jeitos de rodar o servidor:
  - mcp_server.py       (stdio, local, um processo por pessoa)
  - mcp_http_server.py  (HTTP remoto, autenticado via OAuth, hospedado junto com o Flask)

Cada um só precisa fornecer `obter_sessao`: uma função que devolve uma
`requests.Session` já autenticada (com o cookie de sessão do Flask) para o
usuário atual. Toda a lógica de chamar a API JSON do sistema fica aqui, uma
vez só.
"""

from typing import Callable

import requests

FLASK_BASE_URL_PADRAO = 'https://victorjoao271828.pythonanywhere.com'


def registrar_ferramentas(mcp, obter_sessao: Callable[[], requests.Session], base_url: str) -> None:
    base_url = base_url.rstrip('/')

    def _get(path, **kwargs):
        r = obter_sessao().get(f'{base_url}{path}', timeout=10, **kwargs)
        r.raise_for_status()
        return r.json()

    def _post(path, **kwargs):
        r = obter_sessao().post(f'{base_url}{path}', timeout=10, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}

    def _delete(path, **kwargs):
        r = obter_sessao().delete(f'{base_url}{path}', timeout=10, **kwargs)
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
