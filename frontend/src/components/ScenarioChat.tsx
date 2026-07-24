import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, Bot, User } from 'lucide-react'
import plansApi from '@/api/v2/plans'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function ScenarioChat({ scenarioId, planId }: { scenarioId: string; planId: string }) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '你好！我是安迅军事推演AI助手。你可以问我关于当前场景的任何问题，比如实体的位置、关系、状态等。' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    const userMsg: Message = { role: 'user', content: q }
    const updated = [...messages, userMsg]
    setMessages(updated)
    setLoading(true)

    try {
      // Build conversation history (excluding the initial greeting)
      const history = updated
        .filter((_, i) => i > 0) // skip greeting
        .slice(0, -1) // exclude the just-added user message
        .map(m => ({ role: m.role, content: m.content }))

      const res = await plansApi.ask(scenarioId, q, planId, history)
      const answer = (res as any)?.answer || '抱歉，无法获取回答。'
      setMessages(prev => [...prev, { role: 'assistant', content: answer }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '问答服务暂时不可用，请稍后重试。' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full border rounded-lg bg-white">
      {/* Header */}
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b bg-gray-50 flex-shrink-0">
        <Bot size={13} className="text-purple-500" />
        <span className="text-[11px] font-semibold text-gray-600">智能问答</span>
        <span className="text-[10px] text-gray-400 ml-auto">安迅军事 AI</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-0">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-1.5 text-xs ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && (
              <Bot size={12} className="text-purple-500 mt-0.5 flex-shrink-0" />
            )}
            <div className={`px-2 py-1 rounded-lg max-w-[85%] whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700'
            }`}>
              {m.content}
            </div>
            {m.role === 'user' && (
              <User size={12} className="text-blue-500 mt-0.5 flex-shrink-0" />
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-1.5 text-xs">
            <Bot size={12} className="text-purple-500 mt-0.5" />
            <div className="px-2 py-1 rounded-lg bg-gray-100 text-gray-400">
              <Loader2 size={12} className="animate-spin inline mr-1" />
              思考中...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex items-center gap-1 px-2 py-1.5 border-t flex-shrink-0">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="问当前场景的问题..."
          className="flex-1 border rounded px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-purple-400"
          disabled={loading}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || loading}
          className="p-1.5 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-40 flex-shrink-0"
        >
          <Send size={11} />
        </button>
      </div>
    </div>
  )
}
