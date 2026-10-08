import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { isAllowedByEnv } from "./allowed";

/**
 * Exige usuário logado e ainda presente em `ALLOWED_EMAILS`. Toda página e toda consulta ao banco
 * no servidor chamam isto: o proxy sozinho não basta.
 */
export async function requireUser(): Promise<{ email: string; name: string | null }> {
  const session = await auth();
  const email = session?.user?.email;
  if (!email || !isAllowedByEnv(email)) redirect("/login");
  return { email, name: session.user?.name ?? null };
}
