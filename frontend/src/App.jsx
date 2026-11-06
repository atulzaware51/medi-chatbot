import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

import AdminResources from './admin/AdminResources'
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
  const [activeView, setActiveView] = useState(
    () => (typeof window !== 'undefined' && window.location.pathname === '/admin' ? 'admin' : 'chat')
  )
  const [account, setAccount] = useState(null)
  const [csrfToken, setCsrfToken] = useState('')
  const [authLoading, setAuthLoading] = useState(true)
  const [conversations, setConversations] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [error, setError] = useState('')
  const requestControllerRef = useRef(null)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [loading, messages])

  useEffect(
    () => () => requestControllerRef.current?.abort(),
    [],
  )

  const fetchConversation = useCallback(async (id) => {
    const response = await fetch(`/api/chat/conversations/${encodeURIComponent(id)}`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : `Could not restore conversation (HTTP ${response.status}).`,
      )
    }
    setConversationId(data.id)
    setMessages(Array.isArray(data.messages) ? data.messages : [])
  }, [])

  const fetchConversationList = useCallback(async (restoreSelection = true) => {
    const response = await fetch('/api/chat/conversations')
    const data = await response.json().catch(() => [])
    if (!response.ok) {
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : `Could not load chat history (HTTP ${response.status}).`,
      )
    }

    const items = Array.isArray(data) ? data : []
    setConversations(items)
    if (!restoreSelection || !items.length) {
      setConversationId(null)
      setMessages([])
      return
    }

    await fetchConversation(items[0].id)
  }, [fetchConversation])

  async function handleAuthenticated(user) {
    setAccount(user.email)
    setCsrfToken(user.csrf_token)
    setAuthLoading(true)
    setError('')
    try {
      await fetchConversationList()
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load chat history.')
    } finally {
      setAuthLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    async function restoreSession() {
      try {
        const response = await fetch('/api/auth/me')
        if (!response.ok) return
        const user = await response.json()
        if (!active) return
        setAccount(user.email)
        setCsrfToken(user.csrf_token)
        try {
          await fetchConversationList()
        } catch (loadError) {
          if (active) {
            setError(loadError instanceof Error ? loadError.message : 'Could not load chat history.')
          }
        }
      } catch {
        if (active) setError('Unable to connect to Medibot. Please retry.')
      } finally {
        if (active) setAuthLoading(false)
      }
    }
    restoreSession()
    return () => {
      active = false
    }
  }, [fetchConversationList])

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
        window.location.pathname === '/admin' ? 'admin' : 'chat'
      )
    }

    // Keep the selected view in sync when the user navigates with browser back/forward.
    window.addEventListener('popstate', syncViewWithLocation)
    return () => window.removeEventListener('popstate', syncViewWithLocation)
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()

    const text = question.trim()

    // Ignore empty questions and duplicate submissions while loading.
    if (!text || loading) return

    setQuestion('')
    setError('')

    const controller = new AbortController()
    requestControllerRef.current = controller
    setLoading(true)

    try {
      let targetConversationId = conversationId
      if (!targetConversationId) {
        const createResponse = await fetch('/api/chat/conversations', {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrfToken },
        })
        const created = await createResponse.json().catch(() => ({}))
        if (!createResponse.ok) {
          throw new Error(created.detail || `Could not start a conversation (HTTP ${createResponse.status}).`)
        }
        targetConversationId = created.id
        setConversationId(targetConversationId)
        setConversations((current) => [created, ...current])
      }

      setMessages((current) => [...current, { role: 'user', content: text }])
      const response = await fetch(
        `/api/chat/conversations/${encodeURIComponent(targetConversationId)}/messages`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken,
          },
          signal: controller.signal,
          body: JSON.stringify({ question: text }),
        },
      )

      // Extract a useful error message if the API returns a failure.
      if (!response.ok) {
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
      if (controller.signal.aborted) return

      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: data.answer,
          sources: Array.isArray(data.sources) ? data.sources : [],
        },
      ])
      setConversations((current) =>
        current.map((item) =>
          item.id === targetConversationId
            ? {
                ...item,
                title: item.title === 'New conversation'
                  ? text.slice(0, 157)
                  : item.title,
                updated_at: new Date().toISOString(),
              }
            : item,
        ).sort((first, second) =>
          new Date(second.updated_at) - new Date(first.updated_at),
        ),
      )
    } catch (err) {
      if (controller.signal.aborted) return
      setMessages((current) =>
        current.at(-1)?.role === 'user' && current.at(-1)?.content === text
          ? current.slice(0, -1)
          : current,
      )
      // Show connection and backend errors in the chat interface.
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to connect to Medibot. Check that the backend is running.',
      )
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null
        setLoading(false)
      }
    }
  }

  function startNewConversation() {
    const request = requestControllerRef.current
    if (request) {
      requestControllerRef.current = null
      request.abort()
    }

    setConversationId(null)
    setMessages([])
    setQuestion('')
    setError('')
    setLoading(false)
  }

  async function openConversation(conversation) {
    if (loading || historyLoading) return
    setHistoryLoading(true)
    setQuestion('')
    setError('')
    try {
      await fetchConversation(conversation.id)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not restore conversation.')
    } finally {
      setHistoryLoading(false)
    }
  }

  async function deleteConversation(event, id) {
    event.stopPropagation()
    setError('')
    try {
      const response = await fetch(`/api/chat/conversations/${encodeURIComponent(id)}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `Could not delete conversation (HTTP ${response.status}).`)
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not delete conversation.')
      return
    }

    setConversations((current) =>
      current.filter((conversation) => conversation.id !== id),
    )

    if (conversationId === id) {
      setConversationId(null)
      setMessages([])
      setQuestion('')
      setError('')
    }
  }

  async function handleLogout() {
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken },
      })
      if (!response.ok) throw new Error(`Could not sign out (HTTP ${response.status}).`)
      setAccount(null)
      setCsrfToken('')
      setConversations([])
      setConversationId(null)
      setMessages([])
    } catch (logoutError) {
      setError(logoutError instanceof Error ? logoutError.message : 'Could not sign out.')
    }
  }

  async function handleDeleteAccount() {
    const password = window.prompt('Enter your password to permanently delete your account and conversations.')
    if (!password) return
    if (!window.confirm('Delete your account and all saved conversations? This cannot be undone.')) return

    try {
      const response = await fetch('/api/auth/me', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ password }),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || `Could not delete account (HTTP ${response.status}).`)
      }
      setAccount(null)
      setCsrfToken('')
      setConversations([])
      setConversationId(null)
      setMessages([])
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Could not delete account.')
    }
  }

  if (authLoading) {
    return <main className="auth-page" role="status">Loading your secure session…</main>
  }
  if (!account) {
    return <AuthPanel onAuthenticated={handleAuthenticated} />
  }

  return (
    <main className="app-shell">
      {/* Shared header: visible on both the chatbot and admin pages. */}
      <header className="app-header">
        <a className="brand" href="/" aria-label="Medibot home" onClick={(e) => { e.preventDefault(); openChat(); }}>
          <span className="brand-icon" aria-hidden="true">✚</span>
          <span>
            <strong>Medibot</strong>
            <small>Health information assistant</small>
          </span>
        </a>

        <div className="header-actions">
          <span className="account-label">{account}</span>

          {/* Switch to the chatbot. */}
          <button
            className="new-chat-button"
            type="button"
            onClick={openChat}
            aria-pressed={activeView === 'chat'}
          >
            Chat
          </button>

          {/* Open the local admin dashboard directly; remote access requires login. */}
          <button
            className="new-chat-button"
            type="button"
            onClick={openAdmin}
            aria-pressed={activeView === 'admin'}
          >
            Add Resources
          </button>

          {/* Indicate that the application uses the document-grounded API. */}
          <span className="status-indicator">
            <span className="status-dot" />
            Document-grounded AI
          </span>

          {/* Reset the current conversation when requested. */}
          <button
            className="new-chat-button"
            type="button"
            onClick={startNewConversation}
          >
            + New chat
          </button>
          <button
            className="new-chat-button"
            type="button"
            onClick={handleDeleteAccount}
          >
            Delete account
          </button>
          <button
            className="new-chat-button"
            type="button"
            onClick={handleLogout}
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Conditional rendering: show exactly one main page at a time. */}
      {activeView === 'chat' ? (
        // CHAT PAGE
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

            <section className="conversation-history" aria-label="Chat history">
              <h2>Chat history</h2>
              <div className="conversation-list">
                {conversations.length === 0 ? (
                  <p className="history-empty">Your saved chats will appear here.</p>
                ) : (
                  conversations.map((conversation) => (
                    <div className="conversation-history-row" key={conversation.id}>
                      <button
                        className="conversation-history-item"
                        type="button"
                        title={conversation.title}
                        aria-current={conversationId === conversation.id ? 'page' : undefined}
                        disabled={loading || historyLoading}
                        onClick={() => openConversation(conversation)}
                      >
                        {conversation.title}
                      </button>
                      <button
                        className="conversation-delete-button"
                        type="button"
                        aria-label={`Delete ${conversation.title}`}
                        title="Delete conversation"
                        disabled={loading || historyLoading}
                        onClick={(event) =>
                          deleteConversation(event, conversation.id)
                        }
                      >
                        ×
                      </button>
                    </div>
                  ))
                )}
              </div>
            </section>
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

              <span className="privacy-label">Private to your account · 30-day inactivity expiry</span>
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
              <div ref={messagesEndRef} />
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
                disabled={loading || historyLoading}
                onKeyDown={(event) => {
                  // Enter sends; Shift + Enter inserts a new line.
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    event.currentTarget.form?.requestSubmit()
                  }
                }}
              />

              <div className="composer-footer">
                <span>Saved to your account · automatically deleted after 30 days inactive</span>

                {loading ? (
                  <button
                    className="stop-button"
                    type="button"
                    aria-label="Stop response and start a new conversation"
                    title="Stop response"
                    onClick={startNewConversation}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M7 2.5h10L21.5 7v10L17 21.5H7L2.5 17V7z" />
                      <rect x="8" y="8" width="8" height="8" rx="1" />
                    </svg>
                    Stop
                  </button>
                ) : (
                  <button type="submit" disabled={!question.trim() || historyLoading}>
                    Send ↑
                  </button>
                )}
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
      ) : (
        // ADMIN PAGE: render the resource-management component directly.
        <AdminResources />
      )}

      {/* Shared footer: displayed below either page. */}
      <footer className="app-footer">
        Medibot · Retrieval-Augmented Generation · Source-aware responses
      </footer>
    </main>
  )
}
