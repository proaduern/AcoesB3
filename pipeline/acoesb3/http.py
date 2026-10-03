"""Download com registro em source_file (pula arquivo sem mudança)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import psycopg
import requests

USER_AGENT = "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)"


@dataclass
class Downloaded:
    url: str
    content: bytes | None  # None quando o arquivo não mudou desde a última coleta
    source_file_id: int
    last_modified: str | None


def fetch(url: str, retries: int = 4, timeout: int = 300) -> requests.Response:
    delay = 2
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(delay)
            delay *= 2
    raise AssertionError("inalcançável")


def download(
    conn: psycopg.Connection, source: str, url: str, force: bool = False
) -> Downloaded | None:
    """Baixa `url`. Retorna None se o arquivo não existe (404).

    Se o conteúdo for idêntico ao último coletado (mesmo sha256) e `force` for falso,
    devolve `content=None` para o chamador pular o processamento.
    """
    r = fetch(url)
    if r.status_code == 404:
        return None
    content = r.content
    digest = hashlib.sha256(content).hexdigest()
    last_modified = r.headers.get("Last-Modified")
    prev = conn.execute("SELECT id, sha256 FROM source_file WHERE url = %s", (url,)).fetchone()
    if prev and prev[1] == digest and not force:
        return Downloaded(url, None, prev[0], last_modified)
    row = conn.execute(
        """
        INSERT INTO source_file (source, url, last_modified, sha256, size_bytes, collected_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (url) DO UPDATE SET last_modified = EXCLUDED.last_modified,
            sha256 = EXCLUDED.sha256, size_bytes = EXCLUDED.size_bytes, collected_at = now()
        RETURNING id
        """,
        (source, url, last_modified, digest, len(content)),
    ).fetchone()
    return Downloaded(url, content, row[0], last_modified)
