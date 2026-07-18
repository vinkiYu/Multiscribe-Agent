import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import AppLayout from './components/Layout/AppLayout'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Selection from './pages/Selection'
import Generation from './pages/Generation'
import Agents from './pages/Agents'
import KnowledgeBase from './pages/KnowledgeBase'
import History from './pages/History'
import PluginManagement from './pages/PluginManagement'
import TaskManagement from './pages/TaskManagement'
import Logs from './pages/Logs'
import Settings from './pages/Settings'

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <Navigate to='/login' replace />
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <HashRouter>
          <Routes>
            <Route path='/login' element={<Login />} />
            <Route
              path='/*'
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Routes>
                      <Route path='/' element={<Dashboard />} />
                      <Route path='/selection' element={<Selection />} />
                      <Route path='/generation' element={<Generation />} />
                      <Route path='/agents' element={<Agents />} />
                      <Route path='/knowledge' element={<KnowledgeBase />} />
                      <Route path='/history' element={<History />} />
                      <Route path='/plugins' element={<PluginManagement />} />
                      <Route path='/tasks' element={<TaskManagement />} />
                      <Route path='/logs' element={<Logs />} />
                      <Route path='/settings' element={<Settings />} />
                    </Routes>
                  </AppLayout>
                </ProtectedRoute>
              }
            />
          </Routes>
        </HashRouter>
      </AuthProvider>
    </ToastProvider>
  )
}
