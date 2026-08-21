import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, storeTokens } from "../api/client";
import { login } from "../api/endpoints";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await login(password);
      storeTokens(tokens.accessToken, tokens.refreshToken);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Senha incorreta.");
      } else {
        setError("Não foi possível conectar à API local. Ela está rodando?");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-lg"
      >
        <h1 className="text-2xl font-bold">Minha Carteira</h1>
        <p className="mt-1 text-sm text-slate-500">
          Acompanhamento pessoal de investimentos
        </p>

        <label className="mt-6 block text-sm font-medium" htmlFor="password">
          Senha
        </label>
        <input
          id="password"
          type="password"
          autoFocus
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
        />

        {error && (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || password.length === 0}
          className="mt-6 w-full rounded-lg bg-blue-600 py-2.5 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </main>
  );
}
