import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // `next dev` gera um AGENTS.md na raiz quando detecta um agente de código; o repositório não o versiona.
  agentRules: false,
};

export default config;
