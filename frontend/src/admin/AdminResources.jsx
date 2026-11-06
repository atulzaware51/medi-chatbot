import { useCallback, useEffect, useState } from 'react'

// Vite proxies /api requests to the FastAPI backend.
const API_URL = '/api/admin/resources/'
const MAX_UPLOAD_SIZE = 20 * 1024 * 1024

export default function AdminResources() {
  const [resources, setResources] = useState([])
  const [indexState, setIndexState] = useState({
    status: 'not_ready',
    available: false,
    message: 'Loading index status...',
  })
  const [selectedFile, setSelectedFile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [authLoading, setAuthLoading] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)
  const [loginRequired, setLoginRequired] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const fetchResources = useCallback(async () => {
    const response = await fetch(API_URL)
    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : `Could not load resources (HTTP ${response.status}).`,
      )
    }

    return {
      resources: Array.isArray(data.resources) ? data.resources : [],
      index: data.index ?? {
        status: 'not_ready',
        available: false,
        message: 'Index status is unavailable.',
      },
    }
  }, [])

  const loadResources = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await fetchResources()
      setResources(data.resources)
      setIndexState(data.index)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not connect to the Medibot API.',
      )
    } finally {
      setLoading(false)
    }
  }, [fetchResources])

  useEffect(() => {
    let active = true

    fetch(`${API_URL}auth/status`)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(
            typeof data.detail === 'string'
              ? data.detail
              : `Could not check admin login (HTTP ${response.status}).`,
          )
        }
        return data
      })
      .then(async (auth) => {
        if (!active) return
        setLoginRequired(Boolean(auth.login_required))
        if (!auth.configured) {
          setError('Admin login is not configured on the server.')
          return
        }
        if (!auth.authenticated) return

        setAuthenticated(true)
        const data = await fetchResources()
        if (!active) return
        setResources(data.resources)
        setIndexState(data.index)
      })
      .catch((err) => {
        if (!active) return
        setError(
          err instanceof Error
            ? err.message
            : 'Could not connect to the Medibot API.',
        )
      })
      .finally(() => {
        if (active) {
          setLoading(false)
          setAuthLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [fetchResources])

  async function handleLogin(event) {
    event.preventDefault()
    if (!password || authLoading) return

    setAuthLoading(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : `Admin login failed (HTTP ${response.status}).`,
        )
      }

      setAuthenticated(true)
      setPassword('')
      await loadResources()
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Admin login failed.',
      )
    } finally {
      setAuthLoading(false)
    }
  }

  async function handleLogout() {
    setError('')

    try {
      const response = await fetch(`${API_URL}auth/logout`, {
        method: 'POST',
      })
      if (!response.ok) {
        throw new Error(`Admin logout failed (HTTP ${response.status}).`)
      }
      setAuthenticated(false)
      setResources([])
      setPassword('')
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Admin logout failed.',
      )
    }
  }

  async function handleUpload(event) {
    event.preventDefault()

    if (!selectedFile || uploading) return

    const extension = selectedFile.name
      .slice(selectedFile.name.lastIndexOf('.'))
      .toLowerCase()

    if (!['.pdf', '.txt'].includes(extension)) {
      setError('Select a PDF or TXT file.')
      return
    }

    if (selectedFile.size === 0) {
      setError('The selected file is empty.')
      return
    }

    if (selectedFile.size > MAX_UPLOAD_SIZE) {
      setError('The maximum file size is 20 MB.')
      return
    }

    // Multipart upload lets the browser send the file without encoding it as JSON.
    const formData = new FormData()
    formData.append('file', selectedFile)

    setUploading(true)
    setError('')
    setNotice('Uploading and indexing resource. Please wait...')

    try {
      const response = await fetch(`${API_URL}upload`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : `Upload/indexing failed (HTTP ${response.status}).`,
        )
      }

      const filename = data.resource?.name ?? selectedFile.name
      const indexing = data.indexing

      if (indexing?.status === 'indexed') {
        setNotice(
          `Indexed successfully: ${filename}. ` +
          `${indexing.chunks_created} chunks created; ` +
          `${indexing.total_chunks_in_index} total chunks in the index.`,
        )
      } else {
        setNotice(
          `${filename} uploaded, but indexing was not confirmed. ` +
          'Check the backend response.',
        )
      }

      setSelectedFile(null)

      const input = event.currentTarget.querySelector('input[type="file"]')
      if (input) input.value = ''

      // Reload persisted indexing status and per-resource chunk counts after the rebuild.
      await loadResources()
    } catch (err) {
      setNotice('')
      const message =
        err instanceof Error ? err.message : 'Upload/indexing failed.'
      await loadResources()
      setError(message)
    } finally {
      setUploading(false)
    }
  }

  function formatSize(bytes = 0) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }

  const indexStatusLabels = {
    ready: 'Ready',
    building: 'Building',
    failed: 'Failed',
    not_ready: 'Not ready',
  }
  const indexStatusLabel =
    indexStatusLabels[indexState.status] ?? 'Unavailable'

  if (authLoading) {
    return (
      <section className="admin-login-page" role="status">
        Checking admin session...
      </section>
    )
  }

  if (!authenticated) {
    return (
      <section className="admin-login-page">
        <form className="admin-login-card" onSubmit={handleLogin}>
          <p className="eyebrow">RESTRICTED AREA</p>
          <h1>Admin sign in</h1>
          <p>Enter the administrator password to manage knowledge resources.</p>

          <label htmlFor="admin-password">Password</label>
          <input
            id="admin-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            disabled={authLoading}
          />

          {error && <div className="error-message" role="alert">{error}</div>}

          <button type="submit" disabled={!password || authLoading}>
            {authLoading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </section>
    )
  }

  return (
    <section className="admin-page">
      <header className="admin-heading">
        <div>
          <p className="eyebrow">KNOWLEDGE MANAGEMENT</p>
          <h1>Admin Resources</h1>
          <p className="admin-description">
            Upload approved educational resources for Medibot's knowledge base.
          </p>
        </div>

        <button
          className="new-chat-button"
          type="button"
          onClick={loadResources}
          disabled={loading || uploading}
        >
          {loading ? 'Refreshing...' : 'Refresh list'}
        </button>
        {loginRequired && (
          <button
            className="new-chat-button"
            type="button"
            onClick={handleLogout}
            disabled={uploading}
          >
            Log out
          </button>
        )}
      </header>

      <div className="admin-notice">
        <strong>Manage the knowledge base</strong>
        <p>
          Add approved PDF or TXT documents to the local knowledge base.
          Uploads are indexed before they become searchable.
        </p>
      </div>

      <section className="admin-card" aria-label="Knowledge index status">
        <div
          className={`index-state index-state-${indexState.status}`}
          role="status"
          aria-live="polite"
        >
          <span className="index-state-indicator" aria-hidden="true" />
          <div>
            <strong>Knowledge index: {indexStatusLabel}</strong>
            <p>{indexState.message}</p>
          </div>
        </div>
      </section>

      <section className="admin-card">
        <h2>Upload a resource</h2>
        <p className="admin-muted">
          Supported formats: PDF and TXT. Maximum size: 20 MB.
        </p>

        <form className="upload-form" onSubmit={handleUpload}>
          <label htmlFor="resource-file">Choose a document</label>

          <input
            id="resource-file"
            type="file"
            accept=".pdf,.txt,application/pdf,text/plain"
            onChange={(event) => {
              setSelectedFile(event.target.files?.[0] ?? null)
              setError('')
              setNotice('')
            }}
            disabled={loading || uploading}
          />

          {selectedFile && (
            <p className="selected-file">
              Selected: {selectedFile.name} ({formatSize(selectedFile.size)})
            </p>
          )}

          <button
            className="admin-primary-button"
            type="submit"
            disabled={!selectedFile || loading || uploading}
          >
            {uploading ? 'Processing...' : 'Upload and index'}
          </button>
        </form>

        {notice && (
          <div className="admin-success" role="status" aria-live="polite">
            {uploading && (
              <span className="loading-spinner" aria-hidden="true" />
            )}
            {notice}
          </div>
        )}

        {error && (
          <div className="error-message" role="alert">
            {error}
          </div>
        )}
      </section>

      <section className="admin-card">
        <div className="resource-list-heading">
          <div>
            <h2>Available resources</h2>
            <p className="admin-muted">
              {resources.length} supported document
              {resources.length === 1 ? '' : 's'} found
            </p>
          </div>
        </div>

        {loading ? (
          <p className="admin-muted" role="status">
            Loading resources...
          </p>
        ) : resources.length === 0 ? (
          <p className="admin-muted">
            No PDF or TXT resources found. Upload a document to get started.
          </p>
        ) : (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Index status</th>
                  <th>Chunks</th>
                </tr>
              </thead>

              <tbody>
                {resources.map((resource) => {
                  const indexed = resource.index_status === 'indexed'

                  return (
                    <tr key={resource.name}>
                      <td className="resource-filename">{resource.name}</td>

                      <td>
                        {(resource.extension ?? '')
                          .toUpperCase()
                          .replace('.', '')}
                      </td>

                      <td>{formatSize(resource.size_bytes)}</td>

                      <td>
                        <span
                          className={
                            indexed
                              ? 'resource-status resource-status-indexed'
                              : `resource-status resource-status-${resource.index_status ?? 'unknown'}`
                          }
                        >
                          {indexed
                            ? 'Indexed'
                            : resource.index_status === 'pending'
                              ? 'Indexing'
                              : resource.index_status === 'failed'
                                ? 'Indexing failed'
                                : 'Not indexed'}
                        </span>
                      </td>

                      <td>
                        {indexed && Number.isInteger(resource.chunks)
                          ? resource.chunks.toLocaleString()
                          : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="admin-footer-note">
        Only upload documents you are authorized to use. Review medical
        sources for accuracy and suitability before adding them to the
        chatbot's knowledge base.
      </p>
    </section>
  )
}
