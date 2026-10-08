import { redirect } from "next/navigation";
import { auth, signIn } from "@/auth";
import { isAllowedByEnv } from "@/lib/auth/allowed";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  const session = await auth();
  if (isAllowedByEnv(session?.user?.email)) redirect("/");

  return (
    <main className="center">
      <h1>AcoesB3</h1>
      <p>Acesso restrito. Entre com a conta Google autorizada.</p>
      <form
        action={async () => {
          "use server";
          await signIn("google", { redirectTo: "/" });
        }}
      >
        <button type="submit">Entrar com Google</button>
      </form>
    </main>
  );
}
