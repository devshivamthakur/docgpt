import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, ShieldCheck, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { validateEmail, validatePassword } from '../store/validation';

interface FieldError {
  email: string;
  password: string;
}

function LoginPage() {
  const navigate = useNavigate();
  const { login, isLoading, error, clearError } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldError>({ email: '', password: '' });

  const handleBlur = (field: keyof FieldError, value: string) => {
    const validator = field === 'email' ? validateEmail : validatePassword;
    const result = validator(value);
    setFieldErrors((prev) => ({ ...prev, [field]: result.message }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    clearError();

    // Validate all fields before submitting
    const emailResult = validateEmail(email);
    const passwordResult = validatePassword(password);
    setFieldErrors({ email: emailResult.message, password: passwordResult.message });

    if (!emailResult.valid || !passwordResult.valid) return;

    try {
      await login(email, password);
      navigate('/', { replace: true });
    } catch {
      // Error is already set in the store
    }
  };

  const inputClass = (hasError: boolean) =>
    `w-full rounded-xl border bg-slate-800 px-4 py-3 placeholder-slate-500 focus:outline-none ${
      hasError
        ? 'border-red-500/60 focus:border-red-500'
        : 'border-slate-700 focus:border-cyan-500'
    }`;

  return (
    <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
      <div className="w-full max-w-5xl grid md:grid-cols-2 rounded-3xl overflow-hidden border border-slate-800 shadow-2xl">
        <div className="bg-gradient-to-br from-cyan-500 via-slate-900 to-violet-600 p-10 flex flex-col justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/20 px-3 py-1 text-sm">
              <Sparkles className="h-4 w-4" /> DocGPT
            </div>
            <h1 className="mt-8 text-4xl font-semibold">Chat with your documents in seconds.</h1>
            <p className="mt-4 text-sm text-slate-200">Upload files, retrieve context, and ask questions with AI-powered clarity.</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4" /> Secure by design
            </div>
            <p className="mt-2 text-sm text-slate-300">Modern authentication, real-time progress, and a polished workspace for every team.</p>
          </div>
        </div>
        <div className="bg-slate-900 p-10">
          <h2 className="text-2xl font-semibold">Welcome back</h2>
          <p className="mt-2 text-sm text-slate-400">Sign in to continue your document conversations.</p>

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
            <div>
              <input
                className={inputClass(!!fieldErrors.email)}
                placeholder="Email"
                type="email"
                required
                value={email}
                onChange={(e) => { setEmail(e.target.value); setFieldErrors((p) => ({ ...p, email: '' })); }}
                onBlur={() => handleBlur('email', email)}
              />
              {fieldErrors.email && (
                <p className="mt-1 text-xs text-red-400">{fieldErrors.email}</p>
              )}
            </div>
            <div>
              <input
                className={inputClass(!!fieldErrors.password)}
                placeholder="Password"
                type="password"
                required
                value={password}
                onChange={(e) => { setPassword(e.target.value); setFieldErrors((p) => ({ ...p, password: '' })); }}
                onBlur={() => handleBlur('password', password)}
              />
              {fieldErrors.password && (
                <p className="mt-1 text-xs text-red-400">{fieldErrors.password}</p>
              )}
            </div>
            <button
              className="w-full rounded-xl bg-cyan-500 px-4 py-3 font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
              type="submit"
              disabled={isLoading}
            >
              {isLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
          <p className="mt-6 text-sm text-slate-400">
            New here? <Link className="text-cyan-400 hover:underline" to="/register">Create an account</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
