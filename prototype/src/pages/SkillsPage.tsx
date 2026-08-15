import { type ReactElement } from 'react'
import { Blocks, Plus, RefreshCw, Trash } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { skillsApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { SkillEntry } from '../types'

interface SkillsPageProps {
  onFlash: (message: string) => void
}

export function SkillsPage({ onFlash }: SkillsPageProps): ReactElement {
  const remote = useRemoteData<JsonRecord[]>(() => skillsApi.list(), {
    onError: (error) => onFlash(`加载 Skill 失败：${error.message}`),
  })

  const items = (remote.data ?? []) as unknown as SkillEntry[]
  const loading = remote.loading
  const error = remote.error?.message ?? null

  return (
    <>
      <SectionHeading
        icon={<Blocks />}
        title="Agent Skills"
        description="对接 /api/skills：内置 + 自定义 Skill 的清单与 frontmatter。"
        actions={
          <>
            <button
              className="btn"
              type="button"
              onClick={() => void skillsApi.reload().then((res) => onFlash(`已重新扫描：${res.loaded} 个 Skill。`))}
            >
              <RefreshCw /> 重新扫描
            </button>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => createSkill(onFlash)}
            >
              <Plus /> 新建 Skill
            </button>
          </>
        }
      />
      <section className="section">
        <div className="data-table-card">
          {loading ? (
            <div className="empty-state">正在加载 Skill…</div>
          ) : error ? (
            <div className="empty-state">加载失败：{error}</div>
          ) : items.length === 0 ? (
            <div className="empty-state">还没有可用的 Skill，可通过 POST /api/skills 新建一个。</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>标识</th>
                  <th>名称</th>
                  <th>类型</th>
                  <th>说明</th>
                  <th>文件</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {items.map((skill) => (
                  <tr key={skill.id}>
                    <td className="data-table-primary"><strong>{skill.id}</strong></td>
                    <td>{skill.name}</td>
                    <td>
                      <span className={skill.is_builtin ? 'pill pill-builtin' : 'pill pill-custom'}>
                        {skill.is_builtin ? '内置' : '自定义'}
                      </span>
                    </td>
                    <td>{skill.description}</td>
                    <td>
                      <div className="strategy-files">
                        {(skill.files ?? []).slice(0, 3).map((file) => (
                          <span className="pill pill-neutral" key={file}>{file}</span>
                        ))}
                      </div>
                    </td>
                    <td>
                      {!skill.is_builtin && (
                        <button
                          className="btn btn-sm"
                          type="button"
                          onClick={async () => {
                            try {
                              await skillsApi.remove(skill.id)
                              onFlash(`已删除 Skill ${skill.id}。`)
                              await remote.reload()
                            } catch (caught) {
                              onFlash(caught instanceof Error ? caught.message : '删除失败')
                            }
                          }}
                        >
                          <Trash /> 删除
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </>
  )
}

async function createSkill(onFlash: (message: string) => void): Promise<void> {
  const id = window.prompt('Skill id（小写 + 连字符）')
  if (!id) return
  const name = window.prompt('Skill 名称') ?? id
  const description = window.prompt('一句话描述') ?? ''
  const instructions = window.prompt('Skill 指令（可多行）') ?? ''
  try {
    await skillsApi.create({
      id,
      frontmatter: { name, description, bins: [] },
      instructions,
    })
    onFlash(`Skill「${name}」已创建。`)
  } catch (caught) {
    onFlash(caught instanceof Error ? caught.message : '创建失败')
  }
}

export default SkillsPage
