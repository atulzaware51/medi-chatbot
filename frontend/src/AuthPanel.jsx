import { useState } from 'react'

export default function AuthPanel({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (loading) return

    setLoading(true)
    setError('')

    const body = { email, password }
    if (mode === 'register') body.name = name

    try {
      const response = await fetch(`/api/auth/${mode === 'register' ? 'register' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : `Authentication failed (HTTP ${response.status}).`,
        )
      }

      onAuthenticated(data)
      setPassword('')
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to authenticate. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="admin-card admin-login-card">
        <p className="eyebrow">PRIVATE CONVERSATIONS</p>
        <h1>{mode === 'register' ? 'Create your account' : 'Sign in to Medibot'}</h1>
        <p className="admin-muted">
          Your conversations are linked to your account and are not accessible
          to other users.
        </p>
        <form className="upload-form" onSubmit={handleSubmit}>
          {mode === 'register' && (
            <>
              <label htmlFor="account-name">Name</label>
              <input
                id="account-name"
                autoComplete="name"
                maxLength={100}
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </>
          )}
          <label htmlFor="account-email">Email</label>
          <input
            id="account-email"
            type="email"
            autoComplete="email"
            maxLength={254}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="account-password">Password</label>
          <input
            id="account-password"
            type="password"
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            minLength={mode === 'register' ? 12 : 1}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {error && <div className="error-message" role="alert">{error}</div>}
          <button className="admin-primary-button" type="submit" disabled={loading}>
            {loading ? 'Please wait...' : mode === 'register' ? 'Create account' : 'Sign in'}
          </button>
          <button
            className="new-chat-button"
            type="button"
            onClick={() => {
              setMode((current) => current === 'login' ? 'register' : 'login')
              setError('')
            }}
          >
            {mode === 'login' ? 'Create an account' : 'I already have an account'}
          </button>
        </form>
      </div>
    </section>
  )
}
