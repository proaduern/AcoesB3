import { NextResponse } from "next/server";
import { auth } from "@/auth";

// Primeira barreira: sem sessão, vai para o login. A conferência da lista de e-mails fica em
// `requireUser()` (cada página e cada consulta), pois o proxy não protege chamadas diretas ao servidor.
export default auth((req) => {
  if (!req.auth) {
    return NextResponse.redirect(new URL("/login", req.nextUrl.origin));
  }
});

export const config = {
  matcher: ["/((?!api/auth|login|acesso-negado|_next/static|_next/image|favicon.ico).*)"],
};
