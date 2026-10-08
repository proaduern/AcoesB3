/** Lista de e-mails permitidos (`ALLOWED_EMAILS`, separada por vírgula). Falha fechada: lista vazia = ninguém entra. */

export function parseAllowedEmails(raw: string | undefined | null): string[] {
  if (!raw) return [];
  return raw
    .split(/[,;\s]+/)
    .map((e) => e.trim().toLowerCase())
    .filter((e) => e.length > 0);
}

export function isAllowedEmail(
  email: string | undefined | null,
  allowed: readonly string[],
): boolean {
  if (!email) return false;
  return allowed.includes(email.trim().toLowerCase());
}

/** Lê `ALLOWED_EMAILS` a cada chamada: mudar a variável vale sem esperar a sessão expirar. */
export function isAllowedByEnv(email: string | undefined | null): boolean {
  return isAllowedEmail(email, parseAllowedEmails(process.env.ALLOWED_EMAILS));
}
