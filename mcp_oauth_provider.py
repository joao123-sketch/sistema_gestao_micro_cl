"""
Provedor OAuth 2.1 para o servidor MCP remoto (HTTP) do Sistema de Gestão de
Atividades.

Implementa `OAuthAuthorizationServerProvider` do SDK do MCP: o Claude (ou
qualquer cliente MCP) se registra dinamicamente, manda o usuário até a tela
de login em `/oauth/login`, e a partir daí recebe um access token opaco.

Esse servidor NÃO reimplementa a autenticação do Flask — ele faz login em
`{GESTAO_ATIVIDADES_URL}/login` com o usuário/senha digitados na tela e
guarda o cookie de sessão resultante, associado ao access token emitido.
Cada chamada de ferramenta MCP usa esse cookie para falar com a API JSON
já existente do Flask (`/api/...`), então toda a lógica de negócio continua
vivendo só em app.py.

Estado (clientes registrados, códigos e tokens) fica em um banco SQLite
próprio (`mcp_oauth.db`), separado de `atividades.db`.
"""

import os
import secrets
import sqlite3
import time

import requests
from pydantic import AnyUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
OAUTH_DB_FILE = os.path.join(PASTA_ATUAL, 'mcp_oauth.db')

FLASK_BASE_URL = os.environ.get('GESTAO_ATIVIDADES_URL', 'https://victorjoao271828.pythonanywhere.com').rstrip('/')

ACCESS_TOKEN_TTL = 3600
AUTH_CODE_TTL = 300
PENDING_AUTHZ_TTL = 600


def _conn():
    conn = sqlite3.connect(OAUTH_DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_oauth_db():
    conn = _conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS oauth_clients (
            client_id TEXT PRIMARY KEY,
            data      TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS oauth_pending (
            txn                   TEXT PRIMARY KEY,
            client_id             TEXT NOT NULL,
            state                 TEXT,
            scopes                TEXT,
            code_challenge        TEXT NOT NULL,
            redirect_uri          TEXT NOT NULL,
            redirect_uri_explicit INTEGER NOT NULL,
            resource              TEXT,
            expires_at            REAL NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS oauth_codes (
            code                  TEXT PRIMARY KEY,
            client_id             TEXT NOT NULL,
            scopes                TEXT,
            code_challenge        TEXT NOT NULL,
            redirect_uri          TEXT NOT NULL,
            redirect_uri_explicit INTEGER NOT NULL,
            resource              TEXT,
            subject               TEXT,
            flask_cookie          TEXT,
            expires_at            REAL NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            token         TEXT PRIMARY KEY,
            kind          TEXT NOT NULL,
            client_id     TEXT NOT NULL,
            scopes        TEXT,
            resource      TEXT,
            subject       TEXT,
            flask_cookie  TEXT,
            expires_at    REAL,
            paired_token  TEXT
        )
    ''')
    conn.commit()
    conn.close()


def _limpar_expirados(conn):
    agora = time.time()
    conn.execute('DELETE FROM oauth_pending WHERE expires_at < ?', (agora,))
    conn.execute('DELETE FROM oauth_codes WHERE expires_at < ?', (agora,))
    conn.execute('DELETE FROM oauth_tokens WHERE kind = ? AND expires_at IS NOT NULL AND expires_at < ?', ('access', agora))


def carregar_pendencia(txn: str) -> sqlite3.Row | None:
    if not txn:
        return None
    conn = _conn()
    row = conn.execute('SELECT * FROM oauth_pending WHERE txn = ?', (txn,)).fetchone()
    conn.close()
    if not row or row['expires_at'] < time.time():
        return None
    return row


def concluir_login(txn: str, login: str, flask_cookie: str) -> str | None:
    """Troca uma pendência de autorização por um código, após login OK no Flask.

    Retorna a URL de redirecionamento para o cliente MCP, ou None se a
    pendência não existir/tiver expirado.
    """
    pendencia = carregar_pendencia(txn)
    if pendencia is None:
        return None

    codigo = secrets.token_urlsafe(32)
    conn = _conn()
    conn.execute(
        'INSERT INTO oauth_codes (code, client_id, scopes, code_challenge, redirect_uri, '
        'redirect_uri_explicit, resource, subject, flask_cookie, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (
            codigo, pendencia['client_id'], pendencia['scopes'], pendencia['code_challenge'],
            pendencia['redirect_uri'], pendencia['redirect_uri_explicit'], pendencia['resource'],
            login, flask_cookie, time.time() + AUTH_CODE_TTL,
        ),
    )
    conn.execute('DELETE FROM oauth_pending WHERE txn = ?', (txn,))
    conn.commit()
    conn.close()

    return construct_redirect_uri(pendencia['redirect_uri'], code=codigo, state=pendencia['state'])


def autenticar_no_flask(login: str, senha: str) -> str | None:
    """Faz login em {FLASK_BASE_URL}/login e retorna o cookie de sessão, ou None se inválido."""
    sessao = requests.Session()
    resp = sessao.post(f'{FLASK_BASE_URL}/login', data={'login': login, 'senha': senha}, timeout=10)
    resp.raise_for_status()
    if resp.url.rstrip('/').endswith('/login'):
        return None
    return sessao.cookies.get('session')


class GestaoOAuthProvider(OAuthAuthorizationServerProvider):
    """Autoriza contra o login do Flask; emite tokens opacos guardados em SQLite."""

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        conn = _conn()
        row = conn.execute('SELECT data FROM oauth_clients WHERE client_id = ?', (client_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return OAuthClientInformationFull.model_validate_json(row['data'])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        conn = _conn()
        conn.execute(
            'INSERT OR REPLACE INTO oauth_clients (client_id, data) VALUES (?, ?)',
            (client_info.client_id, client_info.model_dump_json()),
        )
        conn.commit()
        conn.close()

    async def authorize(self, client: OAuthClientInformationFull, params) -> str:
        txn = secrets.token_urlsafe(24)
        conn = _conn()
        _limpar_expirados(conn)
        conn.execute(
            'INSERT INTO oauth_pending (txn, client_id, state, scopes, code_challenge, redirect_uri, '
            'redirect_uri_explicit, resource, expires_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (
                txn, client.client_id, params.state, ' '.join(params.scopes or []),
                params.code_challenge, str(params.redirect_uri),
                int(params.redirect_uri_provided_explicitly), params.resource,
                time.time() + PENDING_AUTHZ_TTL,
            ),
        )
        conn.commit()
        conn.close()
        return f'/oauth/login?txn={txn}'

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        conn = _conn()
        row = conn.execute(
            'SELECT * FROM oauth_codes WHERE code = ? AND client_id = ?',
            (authorization_code, client.client_id),
        ).fetchone()
        conn.close()
        if not row or row['expires_at'] < time.time():
            return None
        return AuthorizationCode(
            code=row['code'],
            scopes=(row['scopes'] or '').split(),
            expires_at=row['expires_at'],
            client_id=row['client_id'],
            code_challenge=row['code_challenge'],
            redirect_uri=AnyUrl(row['redirect_uri']),
            redirect_uri_provided_explicitly=bool(row['redirect_uri_explicit']),
            resource=row['resource'],
            subject=row['subject'],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        conn = _conn()
        row = conn.execute('SELECT * FROM oauth_codes WHERE code = ?', (authorization_code.code,)).fetchone()
        if not row:
            conn.close()
            raise TokenError(error='invalid_grant', error_description='Código de autorização inválido ou já usado.')
        conn.execute('DELETE FROM oauth_codes WHERE code = ?', (authorization_code.code,))

        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        agora = time.time()
        self._inserir_par_de_tokens(
            conn, access_token, refresh_token, client.client_id, row['scopes'],
            row['resource'], row['subject'], row['flask_cookie'], agora + ACCESS_TOKEN_TTL,
        )
        conn.commit()
        conn.close()
        return OAuthToken(
            access_token=access_token, token_type='Bearer', expires_in=ACCESS_TOKEN_TTL,
            refresh_token=refresh_token, scope=row['scopes'] or None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE token = ? AND kind = 'refresh' AND client_id = ?",
            (refresh_token, client.client_id),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return RefreshToken(
            token=row['token'], client_id=row['client_id'],
            scopes=(row['scopes'] or '').split(), expires_at=None,
            resource=row['resource'], subject=row['subject'],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        conn = _conn()
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE token = ? AND kind = 'refresh' AND client_id = ?",
            (refresh_token.token, client.client_id),
        ).fetchone()
        if not row:
            conn.close()
            raise TokenError(error='invalid_grant', error_description='Refresh token inválido.')

        conn.execute('DELETE FROM oauth_tokens WHERE token = ? OR token = ?', (row['token'], row['paired_token']))

        novo_access = secrets.token_urlsafe(32)
        novo_refresh = secrets.token_urlsafe(32)
        escopos_concedidos = ' '.join(scopes) if scopes else row['scopes']
        self._inserir_par_de_tokens(
            conn, novo_access, novo_refresh, client.client_id, escopos_concedidos,
            row['resource'], row['subject'], row['flask_cookie'], time.time() + ACCESS_TOKEN_TTL,
        )
        conn.commit()
        conn.close()
        return OAuthToken(
            access_token=novo_access, token_type='Bearer', expires_in=ACCESS_TOKEN_TTL,
            refresh_token=novo_refresh, scope=escopos_concedidos or None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        conn = _conn()
        row = conn.execute("SELECT * FROM oauth_tokens WHERE token = ? AND kind = 'access'", (token,)).fetchone()
        conn.close()
        if not row:
            return None
        if row['expires_at'] and row['expires_at'] < time.time():
            return None
        return AccessToken(
            token=row['token'], client_id=row['client_id'],
            scopes=(row['scopes'] or '').split(),
            expires_at=int(row['expires_at']) if row['expires_at'] else None,
            resource=row['resource'], subject=row['subject'],
            claims={'flask_cookie': row['flask_cookie']} if row['flask_cookie'] else None,
        )

    async def revoke_token(self, token) -> None:
        conn = _conn()
        conn.execute('DELETE FROM oauth_tokens WHERE token = ? OR paired_token = ?', (token.token, token.token))
        conn.commit()
        conn.close()

    @staticmethod
    def _inserir_par_de_tokens(conn, access, refresh, client_id, scopes, resource, subject, flask_cookie, expires_at):
        conn.execute(
            'INSERT INTO oauth_tokens (token, kind, client_id, scopes, resource, subject, flask_cookie, '
            'expires_at, paired_token) VALUES (?,?,?,?,?,?,?,?,?)',
            (access, 'access', client_id, scopes, resource, subject, flask_cookie, expires_at, refresh),
        )
        conn.execute(
            'INSERT INTO oauth_tokens (token, kind, client_id, scopes, resource, subject, flask_cookie, '
            'expires_at, paired_token) VALUES (?,?,?,?,?,?,?,?,?)',
            (refresh, 'refresh', client_id, scopes, resource, subject, flask_cookie, None, access),
        )
