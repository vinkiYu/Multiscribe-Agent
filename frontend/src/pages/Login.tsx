import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle2,
  Database,
  Eye,
  EyeOff,
  FileText,
  GitMerge,
  ScanSearch,
  Send,
} from 'lucide-react'
import { login as loginApi } from '../services/authService'
import { ApiError } from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [connectionState, setConnectionState] = useState<'idle' | 'checking' | 'reachable' | 'error'>('idle')
  const [returningUser] = useState(() => localStorage.getItem('multiscribe_has_logged_in') === 'true')

  useEffect(() => {
    if (localStorage.getItem('multiscribe_token')) {
      navigate('/', { replace: true })
    }
  }, [navigate])

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    setConnectionState('checking')
    try {
      const data = await loginApi(password)
      localStorage.setItem('multiscribe_has_logged_in', 'true')
      setConnectionState('reachable')
      login(data.access_token)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setConnectionState('reachable')
          setError('密码不正确，请重新输入')
        } else if (err.status === 0) {
          setConnectionState('error')
          setError('无法连接 Multiscribe 服务，请确认服务已启动后重试')
        } else {
          setConnectionState('reachable')
          setError(err.message)
        }
      } else {
        setConnectionState('error')
        setError('无法连接 Multiscribe 服务，请确认服务已启动后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className='login-page'>
      <section className='login-brand'>
        <div className='login-data-grid' aria-hidden='true'>
          <span className='data-trace trace-one' />
          <span className='data-trace trace-two' />
          <span className='data-trace trace-three' />
        </div>
        <a className='brand' href='#/'>
          <img className='brand-logo' src='/logo.png' alt='Logo' />
          Multiscribe
        </a>
        <div className='login-brand-content'>
          <div>
            <span className='login-kicker'>{returningUser ? '欢迎回来' : '从一条来源开始'}</span>
            <h1>{returningUser ? '继续管理你的信息处理流程。' : '管理信息来源，生成并发布摘要。'}</h1>
            <p>Multiscribe 帮助你自动采集、生成摘要并按计划推送到团队协作渠道。</p>
          </div>

          <div className='login-workflow' aria-label='Multiscribe 五步处理流程'>
            {[
              { label: '采集', icon: Database },
              { label: '去重', icon: GitMerge },
              { label: '精选', icon: ScanSearch },
              { label: '摘要', icon: FileText },
              { label: '发布', icon: Send },
            ].map(({ label, icon: Icon }, index) => (
              <div className='login-workflow-step' key={label}>
                <span className='workflow-node'>
                  <Icon size={17} aria-hidden='true' />
                </span>
                <span>{label}</span>
                {index < 4 && <i className='workflow-connector' aria-hidden='true' />}
              </div>
            ))}
          </div>
        </div>
        <span className='topbar-meta'>数据由你掌控 · 流程按需组合 · 每次运行都有记录</span>
      </section>
      <section className='login-panel'>
        <form className='login-form' onSubmit={handleSubmit}>
          <div>
            <h2>登录工作台</h2>
            <p className='topbar-meta'>请输入部署 Multiscribe 时设置的管理密码。</p>
          </div>
          <div className='field'>
            <label htmlFor='password'>访问密码</label>
            <div className='password-input-wrap'>
              <input
                className='input'
                id='password'
                type={showPassword ? 'text' : 'password'}
                autoComplete='current-password'
                placeholder='请输入密码'
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
              <button
                className='password-toggle'
                type='button'
                onClick={() => setShowPassword(value => !value)}
                aria-label={showPassword ? '隐藏密码' : '显示密码'}
                title={showPassword ? '隐藏密码' : '显示密码'}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
            <span className='login-field-help'>访问密码由部署者在服务环境变量中设置。</span>
          </div>
          <div className='login-error' role='alert'>{error}</div>
          <button className='btn primary' type='submit' disabled={loading || !password}>
            {loading ? <span className='spinner' /> : '进入 Multiscribe'}
          </button>
          <a className='btn ghost' href='/'>返回官网</a>
          <div className={'login-environment ' + connectionState} role='status' aria-live='polite'>
            <CheckCircle2 size={14} aria-hidden='true' />
            <span>本地实例 · {window.location.hostname || 'localhost'}</span>
            <span className='environment-status'>
              {connectionState === 'checking'
                ? '正在验证 API'
                : connectionState === 'reachable'
                  ? 'API 可访问'
                  : connectionState === 'error'
                    ? 'API 连接异常'
                    : 'API 将在登录时验证'}
            </span>
          </div>
        </form>
      </section>
    </main>
  )
}
