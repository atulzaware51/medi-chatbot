import { useState } from 'react'

export default function AuthPanel({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (loading) return

    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/auth/${mode === 'login' ? 'login' : 'register'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : `Could not ${mode === 'login' ? 'sign in' : 'create account'} (HTTP ${response.status}).`,
        )
      }

      setPassword('')
      onAuthenticated(data)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to connect to Medibot.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="welcome-icon" aria-hidden="true">✚</div>
        <p className="eyebrow">YOUR HEALTH KNOWLEDGE COMPANION</p>
        <h1 id="auth-title">{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
        <p className="auth-description">
          Your conversations are private to your account and are automatically
          deleted after 30 days of inactivity.
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="account-email">Email</label>
          <input
            id="account-email"
            type="email"
            autoComplete="email"
            required
            maxLength={320}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <label htmlFor="account-password">Password</label>
          <input
            id="account-password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            minLength={12}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {mode === 'register' && (
            <small>Use at least 12 characters. Password recovery is not available.</small>
          )}

          {error && <p className="error-message" role="alert">{error}</p>}

          <button type="submit" disabled={loading}>
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <button
          className="auth-mode-toggle"
          type="button"
          onClick={() => {
            setMode((current) => current === 'login' ? 'register' : 'login')
            setError('')
          }}
        >
          {mode === 'login' ? 'New to Medibot? Create an account' : 'Already registered? Sign in'}
        </button>

        <p className="disclaimer">
          Educational information only. Do not enter identifying or sensitive
          health information. Medibot is not a medical professional.
        </p>
      </section>
    </main>
  )
}
