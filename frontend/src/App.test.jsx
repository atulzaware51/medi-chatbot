import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import AuthPanel from './AuthPanel'
import AdminResources from './admin/AdminResources'

function jsonResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  })
}

beforeEach(() => {
  window.history.replaceState({}, '', '/')
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  window.fetch = vi.fn()
})

describe('account access', () => {
  it('submits registration credentials and passes the cookie-backed session to the app', async () => {
    const user = userEvent.setup()
    const onAuthenticated = vi.fn()
    window.fetch.mockReturnValue(
      jsonResponse({ email: 'person@example.com', csrf_token: 'csrf-value' }, 201),
    )
    render(<AuthPanel onAuthenticated={onAuthenticated} />)

    await user.click(screen.getByRole('button', { name: /create an account/i }))
    await user.type(screen.getByLabelText('Email'), 'person@example.com')
    await user.type(screen.getByLabelText('Password'), 'a-long-password-123')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({
      email: 'person@example.com',
      csrf_token: 'csrf-value',
    }))
    expect(window.fetch.mock.calls[0][0]).toBe('/api/auth/register')
    expect(JSON.parse(window.fetch.mock.calls[0][1].body)).toEqual({
      email: 'person@example.com',
      password: 'a-long-password-123',
    })
  })

  it('reports login failures without storing credentials', async () => {
    const user = userEvent.setup()
    window.fetch.mockReturnValue(jsonResponse({ detail: 'Invalid email or password.' }, 401))
    render(<AuthPanel onAuthenticated={vi.fn()} />)
    await user.type(screen.getByLabelText('Email'), 'person@example.com')
    await user.type(screen.getByLabelText('Password'), 'a-long-password-123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
  })
})

describe('server-owned conversation history', () => {
  it('restores a conversation from the server and deletes it there', async () => {
    const summary = {
      id: 'server-conversation-id',
      title: 'What is bone health?',
      created_at: '2026-11-06T00:00:00Z',
      updated_at: '2026-11-06T00:00:00Z',
    }
    window.fetch.mockImplementation((url, options = {}) => {
      if (url === '/api/auth/me') {
        return jsonResponse({ email: 'person@example.com', csrf_token: 'csrf-value' })
      }
      if (url === '/api/chat/conversations') return jsonResponse([summary])
      if (url === `/api/chat/conversations/${summary.id}` && options?.method === 'DELETE') {
        return Promise.resolve({ ok: true, status: 204 })
      }
      if (url === `/api/chat/conversations/${summary.id}`) {
        return jsonResponse({
          ...summary,
          messages: [{ role: 'assistant', content: 'Saved answer.', sources: [] }],
        })
      }
      return jsonResponse({}, 404)
    })
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('Saved answer.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete What is bone health?' }))

    await waitFor(() => {
      expect(window.fetch).toHaveBeenCalledWith(
        `/api/chat/conversations/${summary.id}`,
        expect.objectContaining({
          method: 'DELETE',
          headers: { 'X-CSRF-Token': 'csrf-value' },
        }),
      )
    })
    expect(screen.queryByText('What is bone health?')).not.toBeInTheDocument()
  })

  it('creates server-side conversations and sends a CSRF-protected message', async () => {
    const user = userEvent.setup()
    window.fetch.mockImplementation((url, options = {}) => {
      if (url === '/api/auth/me') {
        return jsonResponse({ email: 'person@example.com', csrf_token: 'csrf-value' })
      }
      if (url === '/api/chat/conversations' && !options.method) return jsonResponse([])
      if (url === '/api/chat/conversations' && options.method === 'POST') {
        return jsonResponse({
          id: 'created-by-server',
          title: 'New conversation',
          created_at: '2026-11-06T00:00:00Z',
          updated_at: '2026-11-06T00:00:00Z',
        }, 201)
      }
      if (url === '/api/chat/conversations/created-by-server/messages') {
        return jsonResponse({
          conversation_id: 'created-by-server',
          question: 'Explain bone health',
          answer: 'A grounded answer.',
          sources: [],
        })
      }
      return jsonResponse({}, 404)
    })
    render(<App />)
    const input = await screen.findByLabelText('Ask Medibot a question')
    await user.type(input, 'Explain bone health')
    await user.click(screen.getByRole('button', { name: 'Send ↑' }))

    expect(await screen.findByText('A grounded answer.')).toBeInTheDocument()
    const messageRequest = window.fetch.mock.calls.find(
      ([url]) => url === '/api/chat/conversations/created-by-server/messages',
    )
    expect(messageRequest[1].headers['X-CSRF-Token']).toBe('csrf-value')
    expect(JSON.parse(messageRequest[1].body)).toEqual({ question: 'Explain bone health' })
  })

  it('keeps failures visible and does not persist transcripts in local storage', async () => {
    const user = userEvent.setup()
    window.fetch.mockImplementation((url, options = {}) => {
      if (url === '/api/auth/me') {
        return jsonResponse({ email: 'person@example.com', csrf_token: 'csrf-value' })
      }
      if (url === '/api/chat/conversations' && !options.method) return jsonResponse([])
      if (url === '/api/chat/conversations' && options.method === 'POST') {
        return jsonResponse({ id: 'server-id', title: 'New conversation' }, 201)
      }
      if (url.endsWith('/messages')) return jsonResponse({ detail: 'Try again later.' }, 503)
      return jsonResponse({}, 404)
    })
    render(<App />)
    const input = await screen.findByLabelText('Ask Medibot a question')
    await user.type(input, 'A private health question')
    await user.click(screen.getByRole('button', { name: 'Send ↑' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again later.')
    expect(window.localStorage.length).toBe(0)
  })
})

describe('admin access', () => {
  it('signs into admin resources with the configured shared password', async () => {
    const user = userEvent.setup()
    window.fetch.mockImplementation((url, options = {}) => {
      if (url.endsWith('auth/status')) {
        return jsonResponse({ configured: true, authenticated: false, login_required: true })
      }
      if (url.endsWith('auth/login')) {
        expect(JSON.parse(options.body)).toEqual({ password: 'admin-password' })
        return jsonResponse({ authenticated: true })
      }
      if (url === '/api/admin/resources/') {
        return jsonResponse({
          resources: [],
          index: { status: 'not_ready', available: false, message: 'No index yet.' },
        })
      }
      return jsonResponse({}, 404)
    })
    render(<AdminResources />)

    const password = await screen.findByLabelText('Password')
    await user.type(password, 'admin-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText(/No index yet/i)).toBeInTheDocument()
  })
})
