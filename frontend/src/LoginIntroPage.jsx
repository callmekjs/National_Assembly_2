import { useState } from 'react'
import { FEATURES } from './appConstants'

export default function LoginIntroPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('아이디와 비밀번호를 입력해 주세요.')
      return
    }
    setError('')
    onLogin({ username: username.trim(), displayName: username.trim() })
  }

  function handleDemoLogin() {
    setError('')
    onLogin({ username: 'demo', displayName: '데모 사용자' })
  }

  return (
    <div className="login-page">
      <div className="login-layout">
        <section className="intro-panel">
          <p className="intro-eyebrow">국회 상임위원회 회의록</p>
          <h1 className="intro-title">회의록으로 확인하는 정책 근거</h1>
          <p className="intro-subtitle">
            발언자, 회의일, 원문 근거를 연결해 정책 쟁점을 빠르게 검토합니다.
          </p>

          <ul className="intro-list">
            <li>전체 회의록에서 관련 발언과 근거를 찾아 정책 질의에 답변합니다.</li>
            <li>답변에는 회의일, 발언자, 참고 근거가 함께 제공됩니다.</li>
            <li>국회·연구기관·정책 실무·언론 리서치 업무에 적합한 검색 환경을 제공합니다.</li>
          </ul>

          <div className="feature-grid">
            {FEATURES.map(f => (
              <div key={f.title} className="feature-item">
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="login-panel">
          <div className="login-box">
            <h2>로그인</h2>
            <p className="login-notice">
              현재는 시연용 로그인입니다. 아이디와 비밀번호를 입력하거나 데모 로그인을 사용할 수 있습니다.
            </p>

            <form onSubmit={handleSubmit} className="login-form">
              <label className="field-label" htmlFor="username">아이디 또는 이메일</label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="user@example.com"
              />

              <label className="field-label" htmlFor="password">비밀번호</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="비밀번호"
              />

              {error && <p className="login-error" role="alert">{error}</p>}

              <button type="submit" className="btn-primary">로그인</button>
              <button type="button" className="btn-secondary" onClick={handleDemoLogin}>
                데모 로그인
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  )
}
