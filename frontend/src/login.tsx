import { StrictMode, useEffect, useState, type FormEvent, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowRight, Eye, EyeOff, KeyRound, LoaderCircle } from 'lucide-react'
import logoUrl from '../multiscribe-logo.png'
import { loginApi } from './services/api'
import './styles.css'

export function Login(): ReactElement {
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (window.localStorage.getItem('multiscribe_token')) {
      window.location.replace('./console.html')
    }
  }, [])

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!password) {
      setError('请输入控制台密码。')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const result = await loginApi(password)
      window.localStorage.setItem('multiscribe_token', result.access_token)
      window.location.assign('./console.html')
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : '登录失败，请稍后重试。')
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <a className="login-brand" href="./index.html" aria-label="返回 Multiscribe 官网">
          <img src={logoUrl} alt="" />
          <span>Multi<b>scribe</b></span>
        </a>
        <div className="login-heading">
          <span className="login-kicker"><KeyRound /> 本地控制台</span>
          <h1 id="login-title">登录后继续工作</h1>
          <p>输入部署时设置的系统密码，进入信息生产工作台。</p>
        </div>
        <form className="login-form" onSubmit={(event) => void submit(event)} noValidate>
          <label htmlFor="password">控制台密码</label>
          <div className="password-control">
            <input
              id="password"
              name="password"
              type={visible ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-describedby={error ? 'login-error' : 'login-help'}
              aria-invalid={Boolean(error)}
              disabled={submitting}
              autoFocus
            />
            <button
              className="password-toggle"
              type="button"
              aria-label={visible ? '隐藏密码' : '显示密码'}
              onClick={() => setVisible((current) => !current)}
              disabled={submitting}
            >
              {visible ? <EyeOff /> : <Eye />}
            </button>
          </div>
          <p id="login-help" className="field-help">密码仅用于本次登录验证，不会保存在浏览器中。</p>
          {error && <p id="login-error" className="field-error" role="alert">{error}</p>}
          <button className="login-submit" type="submit" disabled={submitting}>
            {submitting ? <LoaderCircle className="spin" /> : <ArrowRight />}
            {submitting ? '正在验证' : '登录控制台'}
          </button>
        </form>
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><Login /></StrictMode>)
