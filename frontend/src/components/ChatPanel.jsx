import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, User, Bot, Loader2, Trash2 } from 'lucide-react';

const ChatPanel = () => {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([
    { role: 'agent', content: 'Hello! I am your ERP Intelligence Agent. How can I help you today?' }
  ]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const userMessage = { role: 'user', content: query };
    setMessages(prev => [...prev, userMessage]);
    setQuery('');
    setLoading(true);

    try {
      const response = await axios.post('/api/chat', {
        query: query,
        session_id: 'default'
      });
      
      setMessages(prev => [...prev, { role: 'agent', content: response.data.response }]);
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, { role: 'agent', content: 'Sorry, I encountered an error. Please try again.' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    try {
      await axios.delete('/api/chat/default');
      setMessages([{ role: 'agent', content: 'Conversation cleared. How can I help you now?' }]);
    } catch (error) {
      console.error('Clear error:', error);
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header" style={{
        padding: '16px 24px',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <h2 style={{ fontSize: '16px', fontWeight: '600', margin: 0 }}>ERP Intelligence</h2>
        <button onClick={handleClear} className="text-button" title="Clear History">
          <Trash2 size={16} />
        </button>
      </div>

      <div className="messages-container" style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px'
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex',
            gap: '12px',
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '85%',
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
          }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: msg.role === 'user' ? '#e5e5e5' : '#7c4dff1a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              {msg.role === 'user' ? <User size={18} color="#6b6b6b" /> : <Bot size={18} color="#7c4dff" />}
            </div>
            <div style={{
              backgroundColor: msg.role === 'user' ? 'var(--chat-bubble-user)' : 'var(--chat-bubble-agent)',
              padding: '12px 16px',
              borderRadius: '12px',
              fontSize: '14px',
              lineHeight: '1.6',
              border: msg.role === 'agent' ? '1px solid var(--border-color)' : 'none',
              boxShadow: msg.role === 'agent' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
              whiteSpace: 'pre-wrap'
            }}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '8px',
              backgroundColor: '#7c4dff1a', display: 'flex',
              alignItems: 'center', justifyContent: 'center'
            }}>
              <Bot size={18} color="#7c4dff" />
            </div>
            <div style={{ padding: '12px', display: 'flex', alignItems: 'center' }}>
              <Loader2 size={18} className="spin" color="#7c4dff" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container" style={{
        padding: '24px',
        borderTop: '1px solid var(--border-color)'
      }}>
        <form onSubmit={handleSend} style={{ position: 'relative' }}>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend(e);
              }
            }}
            placeholder="Ask anything about the ERP data..."
            style={{
              width: '100%',
              minHeight: '48px',
              maxHeight: '200px',
              padding: '12px 48px 12px 16px',
              borderRadius: '12px',
              border: '1px solid var(--border-color)',
              fontSize: '14px',
              outline: 'none',
              resize: 'none',
              fontFamily: 'inherit',
              boxShadow: '0 2px 6px rgba(0,0,0,0.02)'
            }}
          />
          <button type="submit" disabled={!query.trim() || loading} style={{
            position: 'absolute',
            right: '12px',
            bottom: '12px',
            background: 'none',
            border: 'none',
            cursor: query.trim() && !loading ? 'pointer' : 'default',
            color: query.trim() && !loading ? 'var(--accent-color)' : '#d1d1d1'
          }}>
            <Send size={20} />
          </button>
        </form>
        <p style={{ fontSize: '11px', color: '#999', textAlign: 'center', marginTop: '12px' }}>
          Built with Anthropic principles & Enterprise Intelligence
        </p>
      </div>

      <style>{`
        .text-button {
          background: none;
          border: none;
          cursor: pointer;
          color: #6b6b6b;
          padding: 4px;
          border-radius: 4px;
        }
        .text-button:hover {
          background: #f2f2f2;
          color: #1a1a1a;
        }
      `}</style>
    </div>
  );
};

export default ChatPanel;
