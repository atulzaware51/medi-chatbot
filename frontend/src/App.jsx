
import { useCallback, useEffect, useState } from 'react'
import './App.css'

// Import the admin dashboard from its actual folder.
import AdminResources from './admin/AdminResources'
import AdminLogin from './admin/AdminLogin'
import AuthPanel from './AuthPanel'

// Display source documents attached to an assistant response.
function Sources({ sources = [] }) {
  const [expanded, setExpanded] = useState(false)

  // Do not display the sources section when no sources are available.
  if (!sources.length) return null

  return (
    <section className="sources">
      {/* Toggle the visibility of the source list. */}
      <button
        type="button"
        className="sources-toggle"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
      >
        <span>📚 Sources ({sources.length})</span>
        <span aria-hidden="true">{expanded ? '−' : '+'}</span>
      </button>

      {/* Render source metadata only when the list is expanded. */}
      {expanded && (
        <ul className="source-list">
          {sources.map((source, index) => (
            <li key={`${source.id}-${source.chunk_id ?? index}`}>
              <strong>{source.id}</strong>
              <span>{source.source}</span>

              {source.page != null && (
                <small>Page {source.page}</small>
              )}

              {source.chunk_id && (
                <small>Chunk: {source.chunk_id}</small>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// Render one user or assistant message.
function Message({ message }) {
  const isUser = message.role === 'user'

  // Highlight answers that mention emergency-care situations.
  const isEmergency =
    message.role === 'assistant' &&
    /medical emergency|emergency department|emergency services/i.test(
      message.content,
    )

  return (
    <article
      className={`message ${isUser ? 'message-user' : 'message-assistant'}`}
    >
      {/* Use a simple avatar to distinguish the speaker. */}
      <div className="message-avatar" aria-hidden="true">
        {isUser ? 'Y' : 'M'}
      </div>

      <div className="message-content">
        <div className="message-label">
          {isUser ? 'You' : 'Medibot'}
        </div>

        {/* Apply special styling to emergency-related responses. */}
        <div
          className={`message-bubble ${isEmergency ? 'emergency-bubble' : ''}`}
        >
          {message.content}
        </div>

        {/* Only assistant messages can show retrieved sources. */}
        {!isUser && <Sources sources={message.sources} />}
      </div>
    </article>
  )
}

export default function App() {
  // Track which page is currently visible: chatbot or admin dashboard.
  const [activeView, setActiveView] = useState(
    window.location.pathname === '/admin' ? 'admin' : 'chat'
  )
  const [adminToken, setAdminToken] = useState(
    () => sessionStorage.getItem('medibot_admin_token') || ''
  )
  const [accessToken, setAccessToken] = useState(
    () => sessionStorage.getItem('medibot_access_token') || ''
  )
  const [currentUser, setCurrentUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(
    () => Boolean(sessionStorage.getItem('medibot_access_token'))
  )
  const [conversations, setConversations] = useState([])
  const [threadId, setThreadId] = useState(null)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const clearAuth = useCallback(() => {
    sessionStorage.removeItem('medibot_access_token')
    setAccessToken('')
    setCurrentUser(null)
    setConversations([])
    setThreadId(null)
    setMessages([])
    setAuthLoading(false)
  }, [])

  const handleAuthenticated = useCallback((data) => {
    sessionStorage.setItem('medibot_access_token', data.access_token)
    setCurrentUser(data.user)
    setAccessToken(data.access_token)
    setAuthLoading(true)
  }, [])

  const handleUserLogout = useCallback(async () => {
    const token = accessToken
    if (!token) {
      clearAuth()
      return
    }

    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        throw new Error(`Logout failed (HTTP ${response.status}).`)
      }
      clearAuth()
    } catch (logoutError) {
      setError(
        logoutError instanceof Error
          ? logoutError.message
          : 'Could not revoke the current session. Please try again.',
      )
    }
  }, [accessToken, clearAuth])

  function navigateTo(path, view) {
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
    }

    setActiveView(view)
  }

  function openAdmin() {
    navigateTo('/admin', 'admin')
  }

  function openChat() {
    navigateTo('/', 'chat')
  }

  useEffect(() => {
    function syncViewWithLocation() {
      setActiveView(
        window.location.pathname === '/admin' ? 'admin' : 'chat',
      )
    }

    window.addEventListener('popstate', syncViewWithLocation)
    return () => window.removeEventListener('popstate', syncViewWithLocation)
  }, [])

  const handleAdminLogout = useCallback(() => {
    sessionStorage.removeItem('medibot_admin_token')
    setAdminToken('')
  }, [])

  function handleAdminLogin(token) {
    sessionStorage.setItem('medibot_admin_token', token)
    setAdminToken(token)
  }

  useEffect(() => {
    if (!accessToken) return undefined

    let active = true
    const headers = { Authorization: `Bearer ${accessToken}` }

    async function restoreAccount() {
      setAuthLoading(true)
      try {
        const userResponse = await fetch('/api/auth/me', { headers })
        if (!userResponse.ok) {
          if (userResponse.status === 401) clearAuth()
          throw new Error('Your session is invalid or has expired. Please sign in again.')
        }

        const user = await userResponse.json()
        const conversationResponse = await fetch('/api/chat/conversations/', { headers })
        if (!conversationResponse.ok) {
          throw new Error(`Could not load conversation history (HTTP ${conversationResponse.status}).`)
        }

        const savedConversations = await conversationResponse.json()
        if (!active) return

        setCurrentUser(user)
        setConversations(savedConversations)
        if (savedConversations.length > 0) {
          const mostRecent = savedConversations[0]
          const messagesResponse = await fetch(
            `/api/chat/conversations/${encodeURIComponent(mostRecent.id)}/messages`,
            { headers },
          )
          if (!messagesResponse.ok) {
            throw new Error(`Could not restore conversation (HTTP ${messagesResponse.status}).`)
          }
          const savedMessages = await messagesResponse.json()
          if (!active) return
          setThreadId(mostRecent.id)
          setMessages(savedMessages)
        } else {
          setThreadId(null)
          setMessages([])
        }
      } catch (restoreError) {
        if (active) {
          setError(
            restoreError instanceof Error
              ? restoreError.message
              : 'Could not restore your account.',
          )
        }
      } finally {
        if (active) setAuthLoading(false)
      }
    }

    restoreAccount()
    return () => {
      active = false
    }
  }, [accessToken, clearAuth])

  async function openConversation(conversationId) {
    if (!accessToken) return

    setError('')
    try {
      const response = await fetch(
        `/api/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
      )
      if (response.status === 401) {
        clearAuth()
        throw new Error('Your session has expired. Please sign in again.')
      }
      if (!response.ok) {
        throw new Error(`Could not open conversation (HTTP ${response.status}).`)
      }

      setThreadId(conversationId)
      setMessages(await response.json())
    } catch (openError) {
      setError(
        openError instanceof Error
          ? openError.message
          : 'Could not open conversation.',
      )
    }
  }

  async function deleteConversation(conversationId) {
    if (!window.confirm('Delete this conversation and its saved messages?')) {
      return
    }

    try {
      const response = await fetch(
        `/api/chat/conversations/${encodeURIComponent(conversationId)}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${accessToken}` },
        },
      )
      if (response.status === 401) {
        clearAuth()
        throw new Error('Your session has expired. Please sign in again.')
      }
      if (!response.ok) {
        throw new Error(`Could not delete conversation (HTTP ${response.status}).`)
      }

      setConversations((current) => current.filter(
        (conversation) => conversation.id !== conversationId,
      ))
      if (threadId === conversationId) {
        setThreadId(null)
        setMessages([])
      }
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : 'Could not delete conversation.',
      )
    }
  }

  // Send the user's question to the existing FastAPI chat endpoint.
  async function handleSubmit(event) {
    event.preventDefault()

    const text = question.trim()

    // Ignore empty questions and duplicate submissions while loading.
    if (!text || loading || !accessToken) return

    setQuestion('')
    setError('')

    // Show the user's message immediately.
    setMessages((current) => [
      ...current,
      { role: 'user', content: text },
    ])

    setLoading(true)

    try {
      let activeThreadId = threadId
      const headers = { Authorization: `Bearer ${accessToken}` }

      if (!activeThreadId) {
        const createResponse = await fetch('/api/chat/conversations/', {
          method: 'POST',
          headers,
        })
        const created = await createResponse.json().catch(() => ({}))
        if (!createResponse.ok) {
          if (createResponse.status === 401) clearAuth()
          throw new Error(
            typeof created.detail === 'string'
              ? created.detail
              : `Could not create conversation (HTTP ${createResponse.status}).`,
          )
        }

        activeThreadId = created.id
        setThreadId(activeThreadId)
        setConversations((current) => [created, ...current])
      }

      // Vite forwards /api/chat/ to the FastAPI /chat/ endpoint.
      const response = await fetch('/api/chat/', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: text,
          thread_id: activeThreadId,
        }),
      })

      // Extract a useful error message if the API returns a failure.
      if (!response.ok) {
        if (response.status === 401) clearAuth()
        let detail = 'Medibot could not process your question.'

        try {
          const data = await response.json()

          if (typeof data.detail === 'string') {
            detail = data.detail
          }
        } catch {
          // Keep the default message when the error is not JSON.
        }

        throw new Error(`${detail} (HTTP ${response.status})`)
      }

      // Read the assistant answer and any retrieved source references.
      const data = await response.json()

      // Append the assistant's response without removing earlier messages.
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: data.answer,
          sources: Array.isArray(data.sources) ? data.sources : [],
        },
      ])
      setConversations((current) => current.map((conversation) => (
        conversation.id === activeThreadId
          ? {
            ...conversation,
            title: conversation.title === 'New conversation'
              ? text.slice(0, 80)
              : conversation.title,
            updated_at: new Date().toISOString(),
          }
          : conversation
      )))
    } catch (err) {
      // Show connection and backend errors in the chat interface.
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to connect to Medibot. Check that the backend is running.',
      )
    } finally {
      // Always release the loading state after the request finishes.
      setLoading(false)
    }
  }

  function startNewConversation() {
    if (loading) return

    setThreadId(null)
    setMessages([])
    setQuestion('')
    setError('')
  }

  function handleNewConversation() {
    openChat()
    startNewConversation()
  }

  return (
    <main className="app-shell">
      {/* Shared header: visible on both the chatbot and admin pages. */}
      <header className="app-header">
        <a className="brand" href="/" aria-label="Medibot home">
          <span className="brand-icon" aria-hidden="true">✚</span>
          <span>
            <strong>Medibot</strong>
            <small>Health information assistant</small>
          </span>
        </a>

        <div className="header-actions">
          {/* Switch to the chatbot without changing the chat implementation. */}
          <button
            className="new-chat-button"
            type="button"
            onClick={openChat}
            aria-pressed={activeView === 'chat'}
          >
            Chat
          </button>

          {/* Open the resource-management dashboard. */}
          <button
            className="new-chat-button"
            type="button"
            onClick={openAdmin}
            aria-pressed={activeView === 'admin'}
          >
            Admin Resources
          </button>

          {/* Indicate that the application uses the document-grounded API. */}
          <span className="status-indicator">
            <span className="status-dot" />
            Document-grounded AI
          </span>
          {currentUser && (
            <>
              <span className="user-label">{currentUser.name}</span>
              <button
                className="new-chat-button"
                type="button"
                onClick={handleUserLogout}
              >
                Sign out
              </button>
            </>
          )}

          {/* Reset the current conversation when requested. */}
          <button
            className="new-chat-button"
            type="button"
            onClick={handleNewConversation}
            disabled={loading}
          >
            + New chat
          </button>
        </div>
      </header>

      {/* Correct conditional rendering: show exactly one main page at a time. */}
      {activeView === 'chat' ? (
        authLoading ? (
          <section className="auth-loading" role="status">
            Restoring your secure session...
          </section>
        ) : !accessToken ? (
          <AuthPanel onAuthenticated={handleAuthenticated} />
        ) : (
          <section className="chat-layout">
          {/* Introductory panel and suggested questions. */}
          <div className="welcome-panel">
            <div className="welcome-icon" aria-hidden="true">✚</div>

            <p className="eyebrow">YOUR HEALTH KNOWLEDGE COMPANION</p>

            <h1>How can I help you learn today?</h1>

            <p className="welcome-description">
              Ask a health-related question. Medibot uses information from
              its indexed documents and shows the available source references.
            </p>

            {/* Clicking a suggestion fills the question field. */}
            <div className="suggestion-list">
              <button
                className="suggestion-button"
                type="button"
                onClick={() =>
                  setQuestion('What is Medibot designed to do?')
                }
                disabled={loading}
              >
                <span>⌕</span>
                What is Medibot designed to do?
              </button>

              <button
                className="suggestion-button"
                type="button"
                onClick={() =>
                  setQuestion(
                    'What information do the documents provide about bone health?',
                  )
                }
                disabled={loading}
              >
                <span>♡</span>
                Learn about bone health
              </button>

              <button
                className="suggestion-button"
                type="button"
                onClick={() =>
                  setQuestion(
                    'What do the indexed documents say about fractures?',
                  )
                }
                disabled={loading}
              >
                <span>▤</span>
                Explore fracture information
              </button>
            </div>

            {conversations.length > 0 && (
              <section className="conversation-history" aria-label="Conversation history">
                <h2>Recent conversations</h2>
                <div className="conversation-list">
                  {conversations.map((conversation) => (
                    <div className="conversation-history-row" key={conversation.id}>
                      <button
                        className="conversation-history-item"
                        type="button"
                        aria-current={threadId === conversation.id ? 'page' : undefined}
                        onClick={() => openConversation(conversation.id)}
                        disabled={loading}
                      >
                        {conversation.title}
                      </button>
                      <button
                        className="conversation-delete-button"
                        type="button"
                        aria-label={`Delete ${conversation.title}`}
                        onClick={() => deleteConversation(conversation.id)}
                        disabled={loading}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Main conversation panel. */}
          <section
            className="chat-panel"
            aria-label="Medibot conversation"
          >
            <div className="chat-toolbar">
              <div>
                <strong>Conversation</strong>
                <small>Your questions and Medibot's answers</small>
              </div>

              <span className="privacy-label">Local API</span>
            </div>

            {/* Display messages, empty state, loading state, or errors. */}
            <div className="messages-area" aria-live="polite">
              {messages.length === 0 && !loading && (
                <div className="empty-state">
                  <span aria-hidden="true">☏</span>
                  <p>Your conversation starts here.</p>
                  <small>Enter a question below to get started.</small>
                </div>
              )}

              {messages.map((message, index) => (
                <Message
                  key={`${message.role}-${index}`}
                  message={message}
                />
              ))}

              {loading && (
                <div className="loading-message" role="status">
                  <span className="loading-dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  Medibot is preparing a response…
                </div>
              )}

              {error && (
                <div className="error-message" role="alert">
                  <strong>Unable to get a response</strong>
                  <p>{error}</p>

                  <button
                    type="button"
                    onClick={() => setError('')}
                  >
                    Dismiss
                  </button>
                </div>
              )}
            </div>

            {/* Question composer submits to handleSubmit(). */}
            <form className="composer" onSubmit={handleSubmit}>
              <label className="sr-only" htmlFor="question-input">
                Ask Medibot a question
              </label>

              <textarea
                id="question-input"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask a health-related question…"
                rows={2}
                maxLength={4000}
                disabled={loading}
                onKeyDown={(event) => {
                  // Enter sends; Shift + Enter inserts a new line.
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    event.currentTarget.form?.requestSubmit()
                  }
                }}
              />

              <div className="composer-footer">
                <span>Enter to send · Shift + Enter for a new line</span>

                <button
                  type="submit"
                  disabled={loading || !question.trim()}
                >
                  {loading ? 'Sending…' : 'Send ↑'}
                </button>
              </div>
            </form>

            {/* Explain the educational limits of the chatbot. */}
            <p className="disclaimer">
              Educational information only. Medibot does not diagnose
              conditions or replace a qualified healthcare professional.
              For a possible emergency, seek immediate medical care.
            </p>
          </section>
          </section>
        )
      ) : (
        adminToken ? (
          <AdminResources
            token={adminToken}
            onLogout={handleAdminLogout}
            onUnauthorized={handleAdminLogout}
          />
        ) : (
          <AdminLogin
            onLogin={handleAdminLogin}
            onBack={openChat}
          />
        )
      )}

      {/* Shared footer: displayed below either page. */}
      <footer className="app-footer">
        Medibot · Retrieval-Augmented Generation · Source-aware responses
      </footer>
    </main>
  )
}
