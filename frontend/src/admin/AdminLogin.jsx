import { useState } from 'react'

const API_URL = '/api/admin/resources/'

export default function AdminLogin({ onLogin, onBack }) {
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!password.trim() || loading) return

    setLoading(true)
    setError('')

    try {
      const response = await fetch(API_URL, {
        headers: { Authorization: `Bearer ${password}` },
      })

      if (response.status === 401) {
        throw new Error('Incorrect admin password.')
      }
      if (response.status === 503) {
        throw new Error('Admin authentication is not configured on the server.')
      }
      if (!response.ok) {
        throw new Error(`Login verification failed (HTTP ${response.status}).`)
      }

      onLogin(password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not verify credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="admin-page">
      <div className="admin-card admin-login-card">
        <p className="eyebrow">MEDIBOT ADMINISTRATION</p>
        <h1>Admin sign in</h1>
        <p className="admin-muted">
          Sign in to manage Medibot's educational knowledge resources.
        </p>
        <form className="upload-form" onSubmit={handleSubmit}>
          <label htmlFor="admin-password">Admin password</label>
          <input
            id="admin-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoFocus
          />
          {error && <div className="error-message" role="alert">{error}</div>}
          <button className="admin-primary-button" type="submit" disabled={loading}>
            {loading ? 'Verifying...' : 'Sign in'}
          </button>
          <button className="new-chat-button" type="button" onClick={onBack}>
            Back to Medibot
          </button>
        </form>
      </div>
    </section>
  )
}
