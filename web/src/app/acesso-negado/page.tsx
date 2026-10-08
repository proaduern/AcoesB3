import Link from "next/link";

export default function AccessDeniedPage() {
  return (
    <main className="center">
      <h1>Acesso negado</h1>
      <p>Esta conta Google não está na lista de e-mails autorizados.</p>
      <p>
        <Link href="/login">Tentar com outra conta</Link>
      </p>
    </main>
  );
}
