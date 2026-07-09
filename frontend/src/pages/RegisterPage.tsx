import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, ShieldCheck, AlertCircle, Check, X } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import {
  validateEmail,
  validatePassword,
  validateName,
  PASSWORD_MIN_LENGTH,
  PASSWORD_PATTERN,
} from '../store/validation';

interface FieldErrors {
  name: string;
  email: string;
  password: string;
}

function getPasswordChecks(password: string) {
  return [
    { label: `At least ${PASSWORD_MIN_LENGTH} characters`, met: password.length >= PASSWORD_MIN_LENGTH },
    { label: 'One uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'One lowercase letter', met: /[a-z]/.test(password) },
    { label: 'One number', met: /\d/.test(password) },
    { label: 'One special character (!@#$%^&*()\-_=+{};:,<.>)', met: /[!@#$%^&*()\-_=+{};:,<.>]/.test(password) },
  ];
}

function RegisterPage() {
  const navigate = useNavigate();
  const { register, isLoading, error, clearError } = useAuthStore();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({ name: '', email: '', password: '' });
  const [passwordTouched, setPasswordTouched] = useState(false);

  const passwordChecks = useMemo(() => getPasswordChecks(password), [password]);

  const handleBlur = (field: keyof FieldErrors, value: string) => {
    let result: { valid: boolean; message: string };
    switch (field) {
      case 'email':
        result = validateEmail(value);
        break;
      case 'name':
        result = validateName(value);
        break;
      case 'password':
        result = validatePassword(value);
        break;
    }
    setFieldErrors((prev) => ({ ...prev, [field]: result.message }));
    if (field === 'password') setPasswordTouched(true);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    clearError();

    const nameResult = validateName(name);
    const emailResult = validateEmail(email);
    const passwordResult = validatePassword(password);
    setFieldErrors({
      name: nameResult.message,
      email: emailResult.message,
      password: passwordResult.message,
    });
    setPasswordTouched(true);

    if (!nameResult.valid || !emailResult.valid || !passwordResult.valid) return;

    try {
      await register(email, password, name);
      navigate('/', { replace: true });
    } catch {
      // Error is already set in the store
    }
  };

  const inputClass = (hasError: boolean) =>
    `w-full rounded-xl border bg-slate-800 px-4 py-3 placeholder-slate-500 focus:outline-none ${
      hasError
        ? 'border-red-500/60 focus:border-red-500'
        : 'border-slate-700 focus:border-violet-500'
    }`;

  return (
    <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
      <div className="w-full max-w-5xl grid md:grid-cols-2 rounded-3xl overflow-hidden border border-slate-800 shadow-2xl">
        <div className="bg-gradient-to-br from-violet-500 via-slate-900 to-cyan-600 p-10 flex flex-col justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/20 px-3 py-1 text-sm">
              <Sparkles className="h-4 w-4" /> Build your knowledge base
            </div>
            <h1 className="mt-8 text-4xl font-semibold">Create a workspace that learns from your docs.</h1>
            <p className="mt-4 text-sm text-slate-200">Everything is designed to feel fast, secure, and genuinely useful.</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="h-4 w-4" /> Protected experience
            </div>
            <p className="mt-2 text-sm text-slate-300">Turn onboarding and file processing into a smooth, modern workflow.</p>
          </div>
        </div>
        <div className="bg-slate-900 p-10">
          <h2 className="text-2xl font-semibold">Start free</h2>
          <p className="mt-2 text-sm text-slate-400">Create your account and upload your first document.</p>

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
            <div>
              <input
                className={inputClass(!!fieldErrors.name)}
                placeholder="Full name"
                required
                value={name}
                onChange={(e) => { setName(e.target.value); setFieldErrors((p) => ({ ...p, name: '' })); }}
                onBlur={() => handleBlur('name', name)}
              />
              {fieldErrors.name && (
                <p className="mt-1 text-xs text-red-400">{fieldErrors.name}</p>
              )}
            </div>

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
                onFocus={() => setPasswordTouched(true)}
                onBlur={() => handleBlur('password', password)}
              />
              {fieldErrors.password && (
                <p className="mt-1 text-xs text-red-400">{fieldErrors.password}</p>
              )}

              {/* Password strength checklist */}
              {passwordTouched && (
                <ul className="mt-2 space-y-1">
                  {passwordChecks.map((check) => (
                    <li key={check.label} className="flex items-center gap-1.5 text-xs text-slate-400">
                      {check.met ? (
                        <Check className="h-3.5 w-3.5 text-green-400" />
                      ) : (
                        <X className="h-3.5 w-3.5 text-slate-500" />
                      )}
                      {check.label}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <button
              className="w-full rounded-xl bg-violet-500 px-4 py-3 font-semibold text-white transition hover:bg-violet-400 disabled:opacity-50"
              type="submit"
              disabled={isLoading}
            >
              {isLoading ? 'Creating account…' : 'Create account'}
            </button>
          </form>
          <p className="mt-6 text-sm text-slate-400">
            Already have an account? <Link className="text-cyan-400 hover:underline" to="/login">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default RegisterPage;
