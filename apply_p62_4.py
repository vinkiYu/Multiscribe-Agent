import sys

with open('prototype/src/shared/ui.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# K2: add moveToMemory button
old_k2 = '<div className="knowledge-row-actions"><time>{formatUnix(document.updated_at)}</time><button className="icon-button danger-button" title="\u5220\u9664\u6587\u6863" aria-label={`\u5220\u9664 ${document.name}`} onClick={() => void removeDocument(document)}><Trash2 /></button></div>'
new_k2 = '<div className="knowledge-row-actions"><time>{formatUnix(document.updated_at)}</time><button className="icon-button" title="\u8f6c\u5165\u8bb0\u5fc6" aria-label={`\u5c06 ${document.name} \u8f6c\u5165\u8bb0\u5fc6`} onClick={() => void moveDocumentToMemory(document)}><BrainCircuit /></button><button className="icon-button danger-button" title="\u5220\u9664\u6587\u6863" aria-label={`\u5220\u9664 ${document.name}`} onClick={() => void removeDocument(document)}><Trash2 /></button></div>'
if old_k2 in content:
    content = content.replace(old_k2, new_k2, 1)
    print('K2 button: OK')
else:
    print('K2 button: NOT FOUND')

# K2: add moveDocumentToMemory function
old_k2_func = "  const removeDocument = async (document: KnowledgeDocument): Promise<void> => {\n    if (!window.confirm(`\u5220\u9664\u201c${document.name}\u201d\u53ca\u5176\u68c0\u7d22\u5185\u5bb9\uff1f`)) return\n    try { await knowledgeApi.remove(document.id); toast.success('\u6587\u6863\u5df2\u5220\u9664'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '\u5220\u9664\u5931\u8d25') }\n  }"
k2_new_func = "\n  const moveDocumentToMemory = async (document: KnowledgeDocument): Promise<void> => {\n    const target = window.prompt(`\u5c06\u201c${document.name}\u201d\u7684\u77e5\u8bc6\u7247\u6bb5\u8f6c\u5165\u8bb0\u5fc6\u7cfb\u7edf\u3002\\n\u8bf7\u8f93\u5165\u76ee\u6807\u8bb0\u5fc6\u5206\u7c7b\uff08\u7559\u7a7a\u4f7f\u7528\u9ed8\u8ba4\u5206\u7c7b\uff09\uff1a`, '')\n    if (target === null) return\n    try { const result = await knowledgeApi.moveToMemory(document.id, target); toast.success(`\u5df2\u8f6c\u5165\u8bb0\u5fc6\uff0c\u5171 ${result.moved_count} \u6761\u7247\u6bb5`); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '\u8f6c\u5165\u8bb0\u5fc6\u5931\u8d25') }\n  }"
if old_k2_func in content:
    content = content.replace(old_k2_func, old_k2_func + k2_new_func, 1)
    print('K2 func: OK')
else:
    print('K2 func: NOT FOUND')

# K1: add file input in KnowledgeTextDialog
old_k1 = '<label>\u77e5\u8bc6\u5185\u5bb9<textarea value={text} placeholder="\u7c98\u8d34\u9700\u8981\u6c89\u6dc0\u7684\u89c4\u5219\u3001\u8d44\u6599\u6216\u8bf4\u660e" onChange={(event) => setText(event.target.value)} /></label>'
new_k1 = old_k1 + '<label>\u4ece\u6587\u4ef6\u5bfc\u5165\uff08\u4ec5 .txt / .md / .markdown\uff09<input type="file" accept=".txt,.md,.markdown" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; if (file.size > 1_000_000) { setError(\'\u6587\u4ef6\u8fc7\u5927\uff08\u8d85\u8fc7 1MB\uff09\uff0c\u8bf7\u76f4\u63a5\u7c98\u8d34\u6587\u672c\u3002\'); return } const reader = new FileReader(); reader.onload = () => { setText(String(reader.result ?? \'\')); setName(name || file.name.replace(/\\.[^.]+$/, \'\')) }; reader.readAsText(file) }} /></label><small>PDF / DOCX \u6682\u4e0d\u652f\u6301\uff0c\u9700\u540e\u7aef\u6587\u4ef6\u4e0a\u4f20\u80fd\u529b\u3002</small>'
if old_k1 in content:
    content = content.replace(old_k1, new_k1, 1)
    print('K1: OK')
else:
    print('K1: NOT FOUND')

# S3+S4: dirty + mask
old_s34_line = "const remote = useRemoteData(settingsApi.get); const [settings, setSettings] = useState<any>(null); const [tab, setTab] = useState<'models' | 'publish' | 'system'>('models'); const [saving, setSaving] = useState(false)\n  useEffect(() => { if (remote.data) setSettings(remote.data) }, [remote.data]); const status = DataStatus({ remote, empty: false }); if (status) return status; if (!settings) return <LoadingState />\n  const save = async (): Promise<void> => { setSaving(true); try { await settingsApi.save(settings); toast.success('\u8bbe\u7f6e\u5df2\u4fdd\u5b58') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '\u8bbe\u7f6e\u4fdd\u5b58\u5931\u8d25') } finally { setSaving(false) } }"
new_s34_line = "const remote = useRemoteData(settingsApi.get); const [settings, setSettings] = useState<any>(null); const [originalSettings, setOriginalSettings] = useState<string>(''); const [tab, setTab] = useState<'models' | 'publish' | 'system'>('models'); const [saving, setSaving] = useState(false)\n  useEffect(() => { if (remote.data) { setSettings(remote.data); setOriginalSettings(JSON.stringify(remote.data)) } }, [remote.data]); const status = DataStatus({ remote, empty: false }); if (status) return status; if (!settings) return <LoadingState />\n  const isDirty = JSON.stringify(settings) !== originalSettings\n  const save = async (): Promise<void> => { const payload = JSON.parse(JSON.stringify(settings)); if (Array.isArray(payload.ai_providers)) { payload.ai_providers = payload.ai_providers.map((p: any) => { if (p.api_key === '********') { const { api_key: _drop, ...rest } = p; return rest } return p }) } setSaving(true); try { await settingsApi.save(payload); setOriginalSettings(JSON.stringify(payload)); toast.success('\u8bbe\u7f6e\u5df2\u4fdd\u5b58') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '\u8bbe\u7f6e\u4fdd\u5b58\u5931\u8d25') } finally { setSaving(false) } }"
if old_s34_line in content:
    content = content.replace(old_s34_line, new_s34_line, 1)
    print('S3+S4: OK')
else:
    print('S3+S4: NOT FOUND')

# S4: update save button disabled (only the last SettingsPageV3 one)
old_save_btn = "disabled={saving} onClick={() => void save()}"
new_save_btn = "disabled={saving || !isDirty} onClick={() => void save()}"
last_idx = content.rfind(old_save_btn)
if last_idx > -1:
    content = content[:last_idx] + new_save_btn + content[last_idx + len(old_save_btn):]
    print('S4 btn: OK')

# S2: add delete button on each publisher card + new publisher button
old_s2_end = '}</article>)}<div className="settings-savebar">'
new_s2_end = '}</article>)}<button className="button" onClick={() => { const newId = `custom-${Date.now()}`; setSettings({ ...settings, publishers: [...settings.publishers, { id: newId, type: \'custom\', enabled: false, config: {} }] }) }}><Plus />\u65b0\u589e\u53d1\u5e03\u6e20\u9053</button><div className="settings-savebar">'
if old_s2_end in content:
    content = content.replace(old_s2_end, new_s2_end, 1)
    print('S2 new: OK')
else:
    print('S2 new: NOT FOUND, trying alternative')
    # Try a more relaxed match
    idx = content.find('settings-savebar')
    if idx > -1:
        # Find the closest publisher </article>) before settings-savebar
        savebar_idx = content.find('<div className="settings-savebar">', idx - 500 if idx > 500 else 0)
        if savebar_idx > -1:
            # Check if there's a publisher </article>)} right before
            before = content[savebar_idx-20:savebar_idx]
            print(f'  before savebar: {repr(before)}')

# S2: add delete button to each publisher header
# Find provider-card-header within SettingsPageV3 publish tab
old_pub_header = '<span className={`status-label ${publisher.enabled ? \'ready\' : \'\'}`}>{publisher.enabled ? \'\u5df2\u542f\u7528\' : \'\u5df2\u505c\u7528\'}</span></div>'
new_pub_header = '<span className={`status-label ${publisher.enabled ? \'ready\' : \'\'}`}>{publisher.enabled ? \'\u5df2\u542f\u7528\' : \'\u5df2\u505c\u7528\'}</span><button className="icon-button danger-button" title="\u5220\u9664\u6e20\u9053" aria-label={`\u5220\u9664 ${publisher.id}`} onClick={() => { if (!window.confirm(`\u5220\u9664\u53d1\u5e03\u6e20\u9053\u201c${publisher.id}\u201d\uff1f`)) return; setSettings({ ...settings, publishers: settings.publishers.filter((_: any, i: number) => i !== index) }) }}><Trash2 /></button></div>'
# Find last occurrence (SettingsPageV3, not V2)
last_pub = content.rfind(old_pub_header)
if last_pub > -1:
    content = content[:last_pub] + new_pub_header + content[last_pub + len(old_pub_header):]
    print('S2 delete: OK')
else:
    print('S2 delete: NOT FOUND')

# P1: PublishingPage filter state
old_p1 = "function PublishingPage(): ReactElement {\n  const [offset, setOffset] = useState(0)\n  const limit = 50\n  const loadPage = useCallback(() => publishHistoryApi.list({ limit, offset }), [offset])\n  const remote = useRemoteData(loadPage)"
new_p1 = "function PublishingPage(): ReactElement {\n  const [offset, setOffset] = useState(0)\n  const [fromDate, setFromDate] = useState('')\n  const [toDate, setToDate] = useState('')\n  const [publisherFilter, setPublisherFilter] = useState('')\n  const limit = 50\n  const loadPage = useCallback(() => publishHistoryApi.list({ limit, offset, from_date: fromDate || undefined, to_date: toDate || undefined, publisher_id: publisherFilter || undefined }), [offset, fromDate, toDate, publisherFilter])\n  const remote = useRemoteData(loadPage)"
if old_p1 in content:
    content = content.replace(old_p1, new_p1, 1)
    print('P1 state: OK')
else:
    print('P1 state: NOT FOUND')

# P1: add publishers extraction + filter UI
old_p1_records = "const records = response.records\n  const currentPage"
new_p1_records = "const records = response.records\n  const publishers = Array.from(new Set(response.records.map((r: PublishHistoryRecord) => r.publisher_id).filter(Boolean)))\n  const currentPage"
if old_p1_records in content:
    content = content.replace(old_p1_records, new_p1_records, 1)
    print('P1 publishers: OK')
else:
    print('P1 publishers: NOT FOUND')

# P1: add filter UI before data-summary
old_p1_return = 'return <section className="data-panel"><div className="data-summary"><Send /><span>\u6295\u9012\u8bb0\u5f55 \u7b2c'
new_p1_return = 'return <section className="data-panel"><div className="publish-filters"><label>\u8d77\u59cb\u65e5\u671f<input type="date" value={fromDate} onChange={(e) => { setFromDate(e.target.value); setOffset(0) }} /></label><label>\u622a\u6b62\u65e5\u671f<input type="date" value={toDate} onChange={(e) => { setToDate(e.target.value); setOffset(0) }} /></label><label>\u53d1\u5e03\u6e20\u9053<select value={publisherFilter} onChange={(e) => { setPublisherFilter(e.target.value); setOffset(0) }}><option value="">\u5168\u90e8\u6e20\u9053</option>{publishers.map((pub) => <option key={pub} value={pub}>{pub}</option>)}</select></label></div><div className="data-summary"><Send /><span>\u6295\u9012\u8bb0\u5f55 \u7b2c'
if old_p1_return in content:
    content = content.replace(old_p1_return, new_p1_return, 1)
    print('P1 filter UI: OK')
else:
    print('P1 filter UI: NOT FOUND')

with open('prototype/src/shared/ui.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('\nAll changes applied')
